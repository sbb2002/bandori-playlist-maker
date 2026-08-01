# 11개 지표 요약 (report_feats.md)

상세는 `method-N-*/out/report/*_findings.md` 참고.

| # | 지표 | 설명 | 결론 |
|---|---|---|---|
| 1 | tempo | 비트 간격으로 잰 BPM | 공식값 94.6% 일치. 5% 배속오차 존재. 순위 신뢰 불가. |
| 2 | key | 크로마로 잰 정확한 조성 | 39.4% 불일치. 근친조 혼동. mode만 활용 권장. |
| 3 | mode | 장조/단조만 추출 | 95.2% 안정. 신뢰 가능. major 우세(56.9%). |
| 4 | loudness | LUFS(음량)+LRA(다이내믹) | 둘 간 약상관(r≈-0.28), 역수 아님. LRA 유망 후보. 청취검증 필요. |
| 5 | energy | 각성도(격함↔차분) | valence 없이 감정 해석 불가. |
| 6 | valence | 정서 밝기(긍정↔부정) | energy 교차 시 90.9% 한 사분면 편중. 변별력 부족. |
| 7 | danceability | 리듬 규칙성(DFA) | 밴드간 차이 작음. tempo·loudness와 무관. lra 결합해야 보조축으로 유의미. |
| 8 | acousticness | 어쿠스틱 확률(proxy) | 95% 0 근접(분포퇴화). 필터 전용, 가중치 부적합. |
| 9 | instrumentalness | 보컬/악기 비중(2종) | voice_median 천장효과로 무용. instr_stem_ratio는 믹싱 밸런스일 뿐 어쿠스틱함과 무관. 이상치 필터용. |
| 10 | liveness | 관중소리+잔향 탐지 | 이스터에그 정답 탐지 실패. rt60 상수화(버그). 폐기 권고. |
| 11 | speechiness | 말하기 vs 노래(2종) | speech_median은 음절밀도 신호로 검증됨. vad_speech_ratio는 도메인 불일치로 오분류 다수. 재정의 보류. |
