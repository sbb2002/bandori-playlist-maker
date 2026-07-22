"""
Generate natural language user queries for lyric_gate_ordering evaluation.

Outputs: out/generated_queries.csv
  Columns: query_id, category, text, keep (empty for manual filtering)

Progress cached in: out/generation_progress.json
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher

import pandas as pd
from groq import Groq, APIError

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROGRESS_PATH = config.OUT_DIR / "generation_progress.json"


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    return {"categories": {}, "started_at": datetime.now(timezone.utc).isoformat()}


def save_progress(progress):
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    PROGRESS_PATH.write_text(
        json.dumps(progress, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def similarity(a, b):
    """Compute string similarity ratio."""
    return SequenceMatcher(None, a, b).ratio()


def has_duplicate(text, existing_texts, threshold=0.85):
    """Check if text is duplicate or highly similar to existing queries."""
    for existing in existing_texts:
        if similarity(text, existing) >= threshold:
            return True
    return False


def retry_with_backoff(func, max_retries=3, base_delay=2.0):
    for attempt in range(max_retries):
        try:
            return func()
        except (APIError, Exception) as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"  Retry {attempt + 1}/{max_retries} after {delay}s ({type(e).__name__})")
                time.sleep(delay)
            else:
                raise


def generate_queries_batch(client, category_key, category_name, count, existing_texts):
    """
    Generate batch of queries for a category using LLM.

    Args:
        client: Groq client
        category_key: One of 'band_specified', 'intensity_brightness', 'situational_functional', 'progressive_arc'
        category_name: Korean name for category
        count: Number of queries to generate
        existing_texts: List of already-generated query texts to avoid duplicates

    Returns:
        List of generated query texts (may be less than count if duplicates excluded)
    """
    band_list = ", ".join(config.VALID_BANDS)

    prompts = {
        "band_specified": (
            f"밴드플레이리스트 앱 사용자들이 입력할 법한 자연어 요청 문구 {count}개를 생성하라.\n\n"
            "카테고리: 밴드지정 (사용자가 특정 밴드를 명시하고, 그 밴드 내에서 상대적 강도/밝기를 요청)\n\n"
            f"유효한 밴드: {band_list}\n\n"
            "예시 문체(참고만, 이것과 똑같이 쓰지 말 것):\n"
            "- poppin'party 노래로 신나게 하루 시작하고 싶어.\n"
            "- roselia 노래 중에 무겁고 진지한 분위기로 틀어줘.\n"
            "- mygo 노래 중에 조용히 감성에 잠기고 싶어.\n\n"
            "특징:\n"
            "- 각 문구는 실제 존재하는 밴드명을 무조건 포함 (존재하지 않는 밴드명 금지)\n"
            "- 상대적 강도/밝기 표현 포함 (예: 조용한, 신나는, 차분한, 격렬한 등)\n"
            "- 반말 자연어, 친근한 톤\n"
            "- 각 문구는 한 줄, 마침표 포함\n\n"
            f"생성 결과 {count}개 문구를 '\n' 구분으로 나열하라. 다른 설명 없이 문구만 출력."
        ),
        "intensity_brightness": (
            f"밴드플레이리스트 앱 사용자들이 입력할 법한 자연어 요청 문구 {count}개를 생성하라.\n\n"
            "카테고리: 강도/밝기 (밴드 명시 없이 절대적인 음량/강도/밝기/감정톤만 요청)\n\n"
            "예시 문체(참고만, 이것과 똑같이 쓰지 말 것):\n"
            "- 완전 조용하고 힘 빠진 노래로 채워줘.\n"
            "- 미친듯이 텐션 폭발하는 노래로 채워줘.\n"
            "- 햇살 가득한 것처럼 밝은 노래 듣고 싶어.\n"
            "- 칠흑같이 어둡고 무거운 노래 듣고 싶어.\n\n"
            "특징:\n"
            "- 밴드명 없음 (또는 '밴드 상관없이' 같은 표현)\n"
            "- 강도 표현 (조용~시끄러움, 약~강), 밝기/감정 표현 (밝음~어두움, 긍정~부정)\n"
            "- 반말 자연어, 친근한 톤\n"
            "- 각 문구는 한 줄, 마침표 포함\n\n"
            f"생성 결과 {count}개 문구를 '\\n' 구분으로 나열하라. 다른 설명 없이 문구만 출력."
        ),
        "situational_functional": (
            f"밴드플레이리스트 앱 사용자들이 입력할 법한 자연어 요청 문구 {count}개를 생성하라.\n\n"
            "카테고리: 상황/기능성 (활동·시간·장소·감정 상황에 맞는 음악)\n\n"
            "예시 문체(참고만, 이것과 똑같이 쓰지 말 것):\n"
            "- 헬스장에서 웨이트 할 때 들을 노래.\n"
            "- 독서할 때 배경으로 틀어놓을 노래.\n"
            "- 친구 생일파티에서 틀 노래.\n"
            "- 잠들기 전 조명 끄고 듣는 노래.\n\n"
            "특징:\n"
            "- 구체적인 활동/시간/상황/감정 표현 (운동/공부/드라이브/파티/휴식/감정 변화 등)\n"
            "- 밴드·강도·밝기 직접 명시 없음\n"
            "- 반말 자연어, 친근한 톤\n"
            "- 각 문구는 한 줄, 마침표 포함\n\n"
            f"생성 결과 {count}개 문구를 '\\n' 구분으로 나열하라. 다른 설명 없이 문구만 출력."
        ),
        "progressive_arc": (
            f"밴드플레이리스트 앱 사용자들이 입력할 법한 자연어 요청 문구 {count}개를 생성하라.\n\n"
            "카테고리: 진행형 아크 (음악의 진행·변화·흐름을 시간대별로 표현)\n\n"
            "예시 문체(참고만, 이것과 똑같이 쓰지 말 것):\n"
            "- 달리기 준비운동부터 본운동, 마무리까지 이어지는 러닝 플레이리스트.\n"
            "- 천천히 달아오르는 파티 분위기로 만들어줘.\n"
            "- 가라앉은 기분에서 서서히 힘을 되찾는 느낌으로.\n"
            "- 새벽 드라이브, 조용히 출발해서 해뜰 때쯤 신나지는 느낌으로.\n\n"
            "특징:\n"
            "- 시간 흐름·변화·진행 표현 (준비→본→마무리, 천천히→점점, 조용→신나는 등)\n"
            "- 시작·중간·끝의 구간적 흐름이나 감정 변화 임시\n"
            "- 반말 자연어, 친근한 톤\n"
            "- 각 문구는 한 줄, 마침표 포함\n\n"
            f"생성 결과 {count}개 문구를 '\\n' 구분으로 나열하라. 다른 설명 없이 문구만 출력."
        ),
    }

    prompt = prompts[category_key]

    def call_generate():
        return client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.GROQ_TEMPERATURE,
        )

    response = retry_with_backoff(call_generate)
    response_text = response.choices[0].message.content.strip()

    # Parse response: split by newline and clean
    lines = [line.strip() for line in response_text.split("\n")]
    lines = [line for line in lines if line and not line.startswith("#")]

    # Filter out duplicates
    new_queries = []
    for line in lines:
        if line and not has_duplicate(line, existing_texts + new_queries):
            new_queries.append(line)

    return new_queries


def main():
    config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    progress = load_progress()

    try:
        api_key = config.get_groq_api_key()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    client = Groq(api_key=api_key)

    # Load existing queries if any
    output_csv = config.OUT_DIR / "generated_queries.csv"
    all_queries = []
    existing_by_cat = {}

    if output_csv.exists():
        df_existing = pd.read_csv(output_csv)
        all_queries = df_existing.to_dict("records")
        for cat in config.CATEGORIES.keys():
            existing_by_cat[cat] = list(
                df_existing[df_existing["category"] == cat]["text"].unique()
            )
    else:
        for cat in config.CATEGORIES.keys():
            existing_by_cat[cat] = []

    # Generate queries for each category
    for category_key, category_name in config.CATEGORIES.items():
        current_count = len(existing_by_cat[category_key])

        if current_count >= config.QUERIES_PER_CATEGORY:
            print(f"[{category_name}] Already has {current_count} queries, skipping")
            continue

        print(f"\n[{category_name}] Generating queries ({current_count}/{config.QUERIES_PER_CATEGORY})...")

        if category_key not in progress["categories"]:
            progress["categories"][category_key] = {"generated": current_count, "rounds": 0}

        # Generate in batches until target reached
        round_num = 0
        while current_count < config.QUERIES_PER_CATEGORY:
            round_num += 1
            needed = config.QUERIES_PER_CATEGORY - current_count
            batch_count = min(config.BATCH_SIZE, needed)

            print(f"  Round {round_num}: Generating {batch_count} queries...")

            try:
                new_queries = generate_queries_batch(
                    client,
                    category_key,
                    category_name,
                    batch_count,
                    existing_by_cat[category_key],
                )

                if not new_queries:
                    print(f"    WARNING: No new queries generated, stopping after {round_num} round(s)")
                    break

                print(f"    Generated {len(new_queries)} unique queries")

                # Add to results
                next_id = len([q for q in all_queries if q["category"] == category_key]) + 1
                for query_text in new_queries:
                    query_id = f"Q{len(all_queries) + 1:04d}"
                    all_queries.append({
                        "query_id": query_id,
                        "category": category_key,
                        "text": query_text,
                        "keep": "",
                    })
                    existing_by_cat[category_key].append(query_text)

                current_count = len(existing_by_cat[category_key])
                progress["categories"][category_key]["generated"] = current_count
                progress["categories"][category_key]["rounds"] = round_num
                save_progress(progress)

                # Save intermediate result
                df_all = pd.DataFrame(all_queries)
                df_all.to_csv(output_csv, index=False, encoding="utf-8-sig")
                print(f"    Saved {len(all_queries)} queries total to {output_csv}")

                if round_num >= 10:
                    print(f"    Max rounds reached, stopping")
                    break

                # Small delay between rounds
                time.sleep(1)

            except Exception as e:
                print(f"  ERROR in round {round_num}: {e}")
                raise

    # Final summary
    df_final = pd.DataFrame(all_queries)
    print(
        f"\n{'='*60}\n"
        f"GENERATION COMPLETE\n"
        f"{'='*60}\n"
        f"Total queries: {len(all_queries)}\n"
    )
    for category_key, category_name in config.CATEGORIES.items():
        cat_count = len(df_final[df_final["category"] == category_key])
        print(f"  {category_name}: {cat_count}")

    print(f"\nResults saved to:\n  {output_csv}\n")
    print("Next step: Open the CSV and set 'keep' column to TRUE/FALSE for filtering.")
    save_progress(progress)


if __name__ == "__main__":
    main()
