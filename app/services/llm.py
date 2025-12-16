import json
import logging
import re
from typing import List

import g4f
import requests
from loguru import logger
from openai import AzureOpenAI, OpenAI
from openai.types.chat import ChatCompletion

from app.config import config

_max_retries = 5


def calculate_video_count(video_script: str) -> int:
    """
    Calculate the number of videos needed based on script word count and narration rate.

    Uses a simple, deterministic formula:
    - Narration time (seconds) = (word_count / narration_rate) × 60
    - Video count = ceil(narration_time / 5) × buffer_factor

    Args:
        video_script: The full video script text

    Returns:
        The recommended number of videos (minimum 1)
    """
    # Configuration constants
    NARRATION_RATE_WPM = 140  # Words per minute - typical speaking pace for narration
    VIDEO_DURATION_SECONDS = 5  # Each video segment is 5 seconds
    BUFFER_FACTOR = 1.3  # 30% buffer to ensure sufficient video coverage

    try:
        # Step 1: Count words in script
        word_count = len(video_script.split())

        # Step 2: Calculate narration duration using simple formula
        # Narration time (seconds) = (W / R) × 60
        narration_time_seconds = (word_count / NARRATION_RATE_WPM) * 60

        # Step 3: Calculate base video count needed
        # Each 5-second video covers one segment
        base_video_count = int(
            (narration_time_seconds + VIDEO_DURATION_SECONDS - 1)
            / VIDEO_DURATION_SECONDS
        )  # Ceiling division

        # Step 4: Apply buffer factor for safety
        buffered_video_count = max(1, int((base_video_count * BUFFER_FACTOR) + 0.5))

        logger.success(
            f"Video count calculation: {word_count} words @ {NARRATION_RATE_WPM} WPM = {narration_time_seconds:.1f}s narration "
            f"→ {base_video_count} base videos → {buffered_video_count} buffered videos (×{BUFFER_FACTOR})"
        )

        return buffered_video_count

    except Exception as e:
        logger.error(f"Error calculating video count: {e}")
        logger.warning("Using default value of 3 videos (minimum for safety)")
        return 3


def generate_multiple_video_prompts(
    video_subject: str, video_script: str, video_count: int
) -> List[str]:
    """
    Generate multiple optimized video prompts by breaking down the script.

    This function creates multiple cinematic prompts (one per video) by analyzing
    the script and generating focused prompts for each segment.

    Args:
        video_subject: The main subject/topic of the video
        video_script: The full script/narration of the video
        video_count: The number of videos/prompts to generate

    Returns:
        A list of optimized prompt strings for video generation

    Raises:
        Exception: If the LLM fails to generate valid prompts
    """
    prompt = f"""# Role: Professional Video Generation Prompt Creator for Multi-Scene Videos

## Goals:
Generate {video_count} distinct, cinematic video prompts by breaking down a script into {video_count} focused segments. Each prompt should represent a coherent visual scene that matches the script pacing.

## Constraints:
1. Return ONLY a JSON array of {video_count} strings.
2. Each string is a complete, detailed video generation prompt (150-200 words each).
3. Do NOT include the JSON array brackets or quotes - format as plain text list separated by newlines and "---" delimiter.
4. Each prompt must:
   - Focus on visual and cinematic elements, not narrative or dialogue
   - Include specific guidance on camera movements, lighting, composition
   - Be distinct and unique from other prompts
   - Represent a coherent 3-5 second visual sequence
   - Flow logically with adjacent prompts
5. Avoid mentioning "video", "camera", or technical terms.
6. Use vivid, descriptive language that evokes emotion and visual clarity.
7. Incorporate cinematography best practices.
8. Do NOT include meta-commentary or instructions about duration.

## Context:

### Main Subject:
{video_subject}

### Full Script:
{video_script}

### Required Output:
Generate exactly {video_count} video prompts. Format each prompt separated by "---" on a new line.

## Instructions:
Analyze the script and break it down into {video_count} natural segments. For each segment, create a comprehensive video generation prompt that visually represents that part of the script. Ensure the prompts flow together as a cohesive narrative when executed sequentially.

Generate the {video_count} prompts now:
""".strip()

    logger.info(f"Generating {video_count} optimized video prompts")

    final_prompts = []

    def format_prompts(response):
        """Parse and clean the generated prompts"""
        if not response:
            return []

        # Split by delimiter
        prompts_raw = response.split("---")

        cleaned_prompts = []
        for prompt_text in prompts_raw:
            # Clean each prompt
            prompt_text = prompt_text.strip()

            # Remove markdown artifacts
            prompt_text = prompt_text.replace("*", "").replace("#", "").replace("`", "")
            prompt_text = re.sub(r"\[.*?\]", "", prompt_text)
            prompt_text = re.sub(r"\(.*?\)", "", prompt_text)

            # Remove excessive whitespace
            prompt_text = re.sub(r"\s+", " ", prompt_text)

            # Remove quotes if they wrap the entire response
            prompt_text = prompt_text.strip("\"'")

            # Remove numbering like "1.", "2.", etc. from the start
            prompt_text = re.sub(r"^\d+\.\s*", "", prompt_text)

            if prompt_text and len(prompt_text) > 80:  # Ensure reasonable length
                cleaned_prompts.append(prompt_text)

        return cleaned_prompts

    for attempt in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            logger.debug(
                f"LLM Response (first 500 chars): {response[:500] if response else 'Empty'}"
            )

            if response and "Error: " not in response:
                parsed_prompts = format_prompts(response)
                logger.debug(f"Parsed {len(parsed_prompts)} prompts from response")

                if (
                    parsed_prompts and len(parsed_prompts) >= video_count * 0.8
                ):  # At least 80% of requested
                    final_prompts = parsed_prompts[:video_count]  # Trim to exact count
                    logger.success(f"Generated {len(final_prompts)} video prompts")
                    return final_prompts
                else:
                    logger.debug(
                        f"Insufficient prompts: got {len(parsed_prompts)}, needed at least {int(video_count * 0.8)}"
                    )
        except Exception as e:
            logger.error(f"Failed to generate video prompts: {e}")
            import traceback

            logger.debug(f"Error traceback: {traceback.format_exc()}")

        if attempt < _max_retries - 1:
            logger.warning(
                f"Retrying prompt generation... {attempt + 1}/{_max_retries}"
            )

    # Fallback: if we couldn't generate all prompts at once, try generating them sequentially
    if not final_prompts or len(final_prompts) < video_count:
        logger.warning(
            f"Fallback: generating prompts sequentially (need {video_count}, have {len(final_prompts)})"
        )

        # Generate individual prompts for each segment
        sequential_prompts = final_prompts.copy() if final_prompts else []

        for segment_num in range(len(sequential_prompts), video_count):
            try:
                segment_prompt = f"""Generate ONE cinematic video prompt for segment {segment_num + 1} of {video_count}.

Subject: {video_subject}

Script segment {segment_num + 1} of {video_count}:
{video_script}

Requirements:
- Return ONLY a single detailed prompt (150-200 words)
- Focus on visual and cinematic elements
- Include camera movements, lighting, composition guidance
- Represent a coherent 3-5 second visual sequence
- No dialogue, no technical terms, no meta-commentary
- Use vivid, descriptive language

Generate the prompt now:"""

                segment_response = _generate_response(prompt=segment_prompt)
                logger.debug(
                    f"Segment {segment_num + 1} response (first 200 chars): {segment_response[:200] if segment_response else 'Empty'}"
                )

                if segment_response and "Error: " not in segment_response:
                    # Clean the response
                    cleaned = segment_response.strip()
                    cleaned = cleaned.replace("*", "").replace("#", "").replace("`", "")
                    cleaned = re.sub(r"\[.*?\]", "", cleaned)
                    cleaned = re.sub(r"\(.*?\)", "", cleaned)
                    cleaned = re.sub(r"\s+", " ", cleaned)
                    cleaned = cleaned.strip("\"'")
                    cleaned = re.sub(r"^\d+\.\s*", "", cleaned)

                    if cleaned and len(cleaned) > 80:
                        sequential_prompts.append(cleaned)
                        logger.success(
                            f"Generated prompt {len(sequential_prompts)}/{video_count}"
                        )

                        # Stop if we have enough
                        if len(sequential_prompts) >= video_count:
                            logger.success(
                                f"Generated all {video_count} prompts sequentially"
                            )
                            return sequential_prompts[:video_count]

            except Exception as e:
                logger.warning(f"Failed to generate segment {segment_num + 1}: {e}")
                continue

        if sequential_prompts:
            logger.warning(
                f"Generated {len(sequential_prompts)} prompts sequentially (needed {video_count})"
            )
            return sequential_prompts[:video_count]

    # Last resort fallback: use the original prompt generation function
    if not final_prompts:
        logger.warning(
            f"Failed to generate {video_count} prompts, generating single fallback prompt"
        )
        fallback_prompt = generate_video_prompt(
            video_subject=video_subject,
            video_script=video_script,
            search_term=video_subject,
        )
        if fallback_prompt and "Error: " not in fallback_prompt:
            return [fallback_prompt]

    return final_prompts


def _generate_response(prompt: str) -> str:
    try:
        content = ""
        llm_provider = config.app.get("llm_provider", "openai")
        logger.info(f"llm provider: {llm_provider}")
        if llm_provider == "g4f":
            model_name = config.app.get("g4f_model_name", "")
            if not model_name:
                model_name = "gpt-3.5-turbo-16k-0613"
            content = g4f.ChatCompletion.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            api_version = ""  # for azure
            if llm_provider == "moonshot":
                api_key = config.app.get("moonshot_api_key")
                model_name = config.app.get("moonshot_model_name")
                base_url = "https://api.moonshot.cn/v1"
            elif llm_provider == "ollama":
                # api_key = config.app.get("openai_api_key")
                api_key = "ollama"  # any string works but you are required to have one
                model_name = config.app.get("ollama_model_name")
                base_url = config.app.get("ollama_base_url", "")
                if not base_url:
                    base_url = "http://localhost:11434/v1"
            elif llm_provider == "openai":
                api_key = config.app.get("openai_api_key")
                model_name = config.app.get("openai_model_name")
                base_url = config.app.get("openai_base_url", "")
                if not base_url:
                    base_url = "https://api.openai.com/v1"
            elif llm_provider == "oneapi":
                api_key = config.app.get("oneapi_api_key")
                model_name = config.app.get("oneapi_model_name")
                base_url = config.app.get("oneapi_base_url", "")
            elif llm_provider == "azure":
                api_key = config.app.get("azure_api_key")
                model_name = config.app.get("azure_model_name")
                base_url = config.app.get("azure_base_url", "")
                api_version = config.app.get("azure_api_version", "2024-02-15-preview")
            elif llm_provider == "gemini":
                api_key = config.app.get("gemini_api_key")
                model_name = config.app.get("gemini_model_name")
                base_url = config.app.get("gemini_base_url", "")
            elif llm_provider == "qwen":
                api_key = config.app.get("qwen_api_key")
                model_name = config.app.get("qwen_model_name")
                base_url = "***"
            elif llm_provider == "cloudflare":
                api_key = config.app.get("cloudflare_api_key")
                model_name = config.app.get("cloudflare_model_name")
                account_id = config.app.get("cloudflare_account_id")
                base_url = "***"
            elif llm_provider == "deepseek":
                api_key = config.app.get("deepseek_api_key")
                model_name = config.app.get("deepseek_model_name")
                base_url = config.app.get("deepseek_base_url")
                if not base_url:
                    base_url = "https://api.deepseek.com"
            elif llm_provider == "modelscope":
                api_key = config.app.get("modelscope_api_key")
                model_name = config.app.get("modelscope_model_name")
                base_url = config.app.get("modelscope_base_url")
                if not base_url:
                    base_url = "https://api-inference.modelscope.cn/v1/"
            elif llm_provider == "ernie":
                api_key = config.app.get("ernie_api_key")
                secret_key = config.app.get("ernie_secret_key")
                base_url = config.app.get("ernie_base_url")
                model_name = "***"
                if not secret_key:
                    raise ValueError(
                        f"{llm_provider}: secret_key is not set, please set it in the config.toml file."
                    )
            elif llm_provider == "pollinations":
                try:
                    base_url = config.app.get("pollinations_base_url", "")
                    if not base_url:
                        base_url = "https://text.pollinations.ai/openai"
                    model_name = config.app.get(
                        "pollinations_model_name", "openai-fast"
                    )

                    # Prepare the payload
                    payload = {
                        "model": model_name,
                        "messages": [{"role": "user", "content": prompt}],
                        "seed": 101,  # Optional but helps with reproducibility
                    }

                    # Optional parameters if configured
                    if config.app.get("pollinations_private"):
                        payload["private"] = True
                    if config.app.get("pollinations_referrer"):
                        payload["referrer"] = config.app.get("pollinations_referrer")

                    headers = {"Content-Type": "application/json"}

                    # Make the API request
                    response = requests.post(base_url, headers=headers, json=payload)
                    response.raise_for_status()
                    result = response.json()

                    if result and "choices" in result and len(result["choices"]) > 0:
                        content = result["choices"][0]["message"]["content"]
                        return content.replace("\n", "")
                    else:
                        raise Exception(
                            f"[{llm_provider}] returned an invalid response format"
                        )

                except requests.exceptions.RequestException as e:
                    raise Exception(f"[{llm_provider}] request failed: {str(e)}")
                except Exception as e:
                    raise Exception(f"[{llm_provider}] error: {str(e)}")

            if llm_provider not in [
                "pollinations",
                "ollama",
            ]:  # Skip validation for providers that don't require API key
                if not api_key:
                    raise ValueError(
                        f"{llm_provider}: api_key is not set, please set it in the config.toml file."
                    )
                if not model_name:
                    raise ValueError(
                        f"{llm_provider}: model_name is not set, please set it in the config.toml file."
                    )
                if not base_url:
                    raise ValueError(
                        f"{llm_provider}: base_url is not set, please set it in the config.toml file."
                    )

            if llm_provider == "qwen":
                import dashscope
                from dashscope.api_entities.dashscope_response import GenerationResponse

                dashscope.api_key = api_key
                response = dashscope.Generation.call(
                    model=model_name, messages=[{"role": "user", "content": prompt}]
                )
                if response:
                    if isinstance(response, GenerationResponse):
                        status_code = response.status_code
                        if status_code != 200:
                            raise Exception(
                                f'[{llm_provider}] returned an error response: "{response}"'
                            )

                        content = response["output"]["text"]
                        return content.replace("\n", "")
                    else:
                        raise Exception(
                            f'[{llm_provider}] returned an invalid response: "{response}"'
                        )
                else:
                    raise Exception(f"[{llm_provider}] returned an empty response")

            if llm_provider == "gemini":
                import google.generativeai as genai

                if not base_url:
                    genai.configure(api_key=api_key, transport="rest")
                else:
                    genai.configure(
                        api_key=api_key,
                        transport="rest",
                        client_options={"api_endpoint": base_url},
                    )

                generation_config = {
                    "temperature": 0.5,
                    "top_p": 1,
                    "top_k": 1,
                    "max_output_tokens": 2048,
                }

                safety_settings = [
                    {
                        "category": "HARM_CATEGORY_HARASSMENT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_HATE_SPEECH",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                    {
                        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                        "threshold": "BLOCK_ONLY_HIGH",
                    },
                ]

                model = genai.GenerativeModel(
                    model_name=model_name,
                    generation_config=generation_config,
                    safety_settings=safety_settings,
                )

                try:
                    response = model.generate_content(prompt)
                    candidates = response.candidates
                    generated_text = candidates[0].content.parts[0].text
                except (AttributeError, IndexError) as e:
                    print("Gemini Error:", e)

                return generated_text

            if llm_provider == "cloudflare":
                response = requests.post(
                    f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_name}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a friendly assistant",
                            },
                            {"role": "user", "content": prompt},
                        ]
                    },
                )
                result = response.json()
                logger.info(result)
                return result["result"]["response"]

            if llm_provider == "ernie":
                response = requests.post(
                    "https://aip.baidubce.com/oauth/2.0/token",
                    params={
                        "grant_type": "client_credentials",
                        "client_id": api_key,
                        "client_secret": secret_key,
                    },
                )
                access_token = response.json().get("access_token")
                url = f"{base_url}?access_token={access_token}"

                payload = json.dumps(
                    {
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.5,
                        "top_p": 0.8,
                        "penalty_score": 1,
                        "disable_search": False,
                        "enable_citation": False,
                        "response_format": "text",
                    }
                )
                headers = {"Content-Type": "application/json"}

                response = requests.request(
                    "POST", url, headers=headers, data=payload
                ).json()
                return response.get("result")

            if llm_provider == "azure":
                client = AzureOpenAI(
                    api_key=api_key,
                    api_version=api_version,
                    azure_endpoint=base_url,
                )

            if llm_provider == "modelscope":
                content = ""
                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body={"enable_thinking": False},
                    stream=True,
                )
                if response:
                    for chunk in response:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            content += delta.content

                    if not content.strip():
                        raise ValueError("Empty content in stream response")

                    return content.replace("\n", "")
                else:
                    raise Exception(f"[{llm_provider}] returned an empty response")

            else:
                client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                )

            response = client.chat.completions.create(
                model=model_name, messages=[{"role": "user", "content": prompt}]
            )
            if response:
                if isinstance(response, ChatCompletion):
                    content = response.choices[0].message.content
                else:
                    raise Exception(
                        f'[{llm_provider}] returned an invalid response: "{response}", please check your network '
                        f"connection and try again."
                    )
            else:
                raise Exception(
                    f"[{llm_provider}] returned an empty response, please check your network connection and try again."
                )

        return content.replace("\n", "")
    except Exception as e:
        return f"Error: {str(e)}"


def generate_script(
    video_subject: str, language: str = "", paragraph_number: int = 1
) -> str:
    prompt = f"""
# Role: Video Script Generator

## Goals:
Generate a script for a video, depending on the subject of the video.

## Constrains:
1. the script is to be returned as a string with the specified number of paragraphs.
2. do not under any circumstance reference this prompt in your response.
3. get straight to the point, don't start with unnecessary things like, "welcome to this video".
4. you must not include any type of markdown or formatting in the script, never use a title.
5. only return the raw content of the script.
6. do not include "voiceover", "narrator" or similar indicators of what should be spoken at the beginning of each paragraph or line.
7. you must not mention the prompt, or anything about the script itself. also, never talk about the amount of paragraphs or lines. just write the script.
8. respond in the same language as the video subject.

# Initialization:
- video subject: {video_subject}
- number of paragraphs: {paragraph_number}
""".strip()
    if language:
        prompt += f"\n- language: {language}"

    final_script = ""
    logger.info(f"subject: {video_subject}")

    def format_response(response):
        # Clean the script
        # Remove asterisks, hashes
        response = response.replace("*", "")
        response = response.replace("#", "")

        # Remove markdown syntax
        response = re.sub(r"\[.*\]", "", response)
        response = re.sub(r"\(.*\)", "", response)

        # Split the script into paragraphs
        paragraphs = response.split("\n\n")

        # Select the specified number of paragraphs
        # selected_paragraphs = paragraphs[:paragraph_number]

        # Join the selected paragraphs into a single string
        return "\n\n".join(paragraphs)

    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                final_script = format_response(response)
            else:
                logging.error("gpt returned an empty response")

            # g4f may return an error message
            if final_script and "当日额度已消耗完" in final_script:
                raise ValueError(final_script)

            if final_script:
                break
        except Exception as e:
            logger.error(f"failed to generate script: {e}")

        if i < _max_retries:
            logger.warning(f"failed to generate video script, trying again... {i + 1}")
    if "Error: " in final_script:
        logger.error(f"failed to generate video script: {final_script}")
    else:
        logger.success(f"completed: \n{final_script}")
    return final_script.strip()


def generate_terms(video_subject: str, video_script: str, amount: int = 5) -> List[str]:
    prompt = f"""
# Role: Video Search Terms Generator

## Goals:
Generate {amount} search terms for stock videos, depending on the subject of a video.

## Constrains:
1. the search terms are to be returned as a json-array of strings.
2. each search term should consist of 1-3 words, always add the main subject of the video.
3. you must only return the json-array of strings. you must not return anything else. you must not return the script.
4. the search terms must be related to the subject of the video.
5. reply with english search terms only.

## Output Example:
["search term 1", "search term 2", "search term 3","search term 4","search term 5"]

## Context:
### Video Subject
{video_subject}

### Video Script
{video_script}

Please note that you must use English for generating video search terms; Chinese is not accepted.
""".strip()

    logger.info(f"subject: {video_subject}")

    search_terms = []
    response = ""
    for i in range(_max_retries):
        try:
            response = _generate_response(prompt)
            if "Error: " in response:
                logger.error(f"failed to generate video script: {response}")
                return response
            search_terms = json.loads(response)
            if not isinstance(search_terms, list) or not all(
                isinstance(term, str) for term in search_terms
            ):
                logger.error("response is not a list of strings.")
                continue

        except Exception as e:
            logger.warning(f"failed to generate video terms: {str(e)}")
            if response:
                match = re.search(r"\[.*]", response)
                if match:
                    try:
                        search_terms = json.loads(match.group())
                    except Exception as e:
                        logger.warning(f"failed to generate video terms: {str(e)}")
                        pass

        if search_terms and len(search_terms) > 0:
            break
        if i < _max_retries:
            logger.warning(f"failed to generate video terms, trying again... {i + 1}")

    logger.success(f"completed: \n{search_terms}")
    return search_terms


def generate_video_prompt(
    video_subject: str, video_script: str, search_term: str
) -> str:
    """
    Generate an optimized video prompt for Replicate's video generation model.

    This function creates a detailed, cinematic prompt specifically designed for
    the bytedance/seedance-1-pro model on Replicate, incorporating the video subject,
    script context, and search terms to produce high-quality video generation results.

    Args:
        video_subject: The main subject/topic of the video
        video_script: The full script/narration of the video
        search_term: A search term/keyword related to the video content

    Returns:
        An optimized prompt string for video generation

    Raises:
        Exception: If the LLM fails to generate a valid prompt
    """
    prompt = f"""# Role: Professional Video Generation Prompt Creator

## Goals:
Generate a highly detailed, cinematic video prompt for AI video generation that captures the essence of the provided content. The prompt should be optimized for professional video generation models and include rich visual descriptions, cinematography guidance, and atmospheric elements.

## Constraints:
1. The prompt must be returned as a single, cohesive string without markdown or special formatting.
2. Maximum 200-250 words, but be as descriptive as possible within this limit.
3. Focus on visual and cinematic elements, not narrative or dialogue.
4. Include specific guidance on:
   - Camera movements and angles
   - Lighting and atmosphere
   - Color palette and mood
   - Pacing and transitions
   - Visual composition and framing
5. Avoid mentioning "video", "camera", or technical terms that might confuse the model.
6. Use vivid, descriptive language that evokes emotion and visual clarity.
7. Be specific about the environment, objects, and actions rather than abstract concepts.
8. Incorporate cinematography best practices (rule of thirds, depth of field, motion etc).
9. Do NOT include instructions about duration, aspect ratio, or technical parameters.
10. Do NOT include dialogue or narrator instructions.
11. Do NOT mention that this is for AI generation or include meta-commentary.
12. Return ONLY the prompt text, nothing else.

## Context Information:

### Main Subject:
{video_subject}

### Video Script/Narration:
{video_script}

### Primary Keyword:
{search_term}

## Output Requirements:
- Create a vivid, cinematic prompt that visually represents the script content
- The prompt should inspire rich, high-quality visuals when used with a video generation model
- Use sensory and visual language that creates a clear mental image
- Include specific visual scenarios, environments, and compositions
- Ensure the prompt feels professional and cinematically coherent

## Instructions:
Based on the subject, script, and keyword provided above, generate a comprehensive video generation prompt that translates the narrative content into visual instructions. The prompt should guide the video model to create compelling, high-quality visuals that match the tone and content of the script.
""".strip()

    logger.info(f"Generating optimized video prompt for: {video_subject}")
    logger.info(f"Search term: {search_term}")

    final_prompt = ""

    def format_prompt(response):
        """Clean and format the generated prompt"""
        # Remove markdown artifacts
        response = response.replace("*", "").replace("#", "").replace("`", "")

        # Remove common markdown patterns
        response = re.sub(r"\[.*?\]", "", response)
        response = re.sub(r"\(.*?\)", "", response)

        # Clean up excessive whitespace
        response = re.sub(r"\s+", " ", response)

        # Remove quotes if they wrap the entire response
        response = response.strip("\"'")

        return response.strip()

    for i in range(_max_retries):
        try:
            response = _generate_response(prompt=prompt)
            if response:
                final_prompt = format_prompt(response)
            else:
                logger.error("LLM returned an empty response for video prompt")

            if final_prompt and "Error: " not in final_prompt:
                if len(final_prompt) > 100:  # Ensure reasonable length
                    break
        except Exception as e:
            logger.error(f"Failed to generate video prompt: {e}")

        if i < _max_retries - 1:
            logger.warning(
                f"Failed to generate video prompt, retrying... {i + 1}/{_max_retries}"
            )

    if "Error: " in final_prompt:
        logger.error(f"Failed to generate video prompt: {final_prompt}")
    else:
        logger.success(f"Video prompt generated successfully:\n{final_prompt}")

    return final_prompt.strip()


if __name__ == "__main__":
    video_subject = "生命的意义是什么"
    script = generate_script(
        video_subject=video_subject, language="zh-CN", paragraph_number=1
    )
    print("######################")
    print(script)
    search_terms = generate_terms(
        video_subject=video_subject, video_script=script, amount=5
    )
    print("######################")
    print(search_terms)
