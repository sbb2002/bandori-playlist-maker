# bpm_madmom vs Bestdori 공식 BPM 비교

Bestdori 매칭 곡수: 573 / 736 (커버곡 등 미매칭 제외)
오차 8% 이내 일치: 542곡 (94.6%)
불일치: 31곡 (5.4%) — 이 중 배속(2x) 13곡, 반절(0.5x) 14곡
불일치 곡 중 halftime_flag=True로 이미 잡힌 것: 11/31 (35%) — **즉 halftime_flag는 옥타브 오차 탐지 신뢰도가 낮다.**

## 밴드별 불일치율 (표본 5곡 미만 제외, 불일치율 내림차순)

| band | n | 불일치 | 불일치율 |
|---|---|---|---|
| ave_mujica | 9 | 2 | 22.2% |
| mygo | 31 | 4 | 12.9% |
| raise_a_suilen | 72 | 6 | 8.3% |
| hello_happy_world | 71 | 5 | 7.0% |
| poppin_party | 107 | 5 | 4.7% |
| roselia | 87 | 4 | 4.6% |
| pastel_palettes | 74 | 3 | 4.1% |
| morfonica | 52 | 1 | 1.9% |
| afterglow | 70 | 1 | 1.4% |

## 불일치 곡 목록 (ratio 오름차순)

| idx | band | song | bpm_madmom | official_bpm | ratio | octave_class | halftime_flag |
|---|---|---|---|---|---|---|---|
| 150 | hello_happy_world | スマイリーキャロル | 109.1 | 220.0 | 0.496 | half(0.5x) | False |
| 464 | poppin_party | フィクション (Cover) | 122.4 | 246.0 | 0.498 | half(0.5x) | False |
| 169 | hello_happy_world | GO! GO! MANIAC (Cover) | 125.0 | 250.0 | 0.500 | half(0.5x) | False |
| 213 | morfonica | 胡蝶翔る星月夜 | 100.0 | 200.0 | 0.500 | half(0.5x) | False |
| 514 | raise_a_suilen | Life on the Lotus | 101.7 | 203.0 | 0.501 | half(0.5x) | False |
| 497 | raise_a_suilen | DRIVE US CRAZY | 105.3 | 210.0 | 0.501 | half(0.5x) | False |
| 418 | poppin_party | Home Street | 105.3 | 210.0 | 0.501 | half(0.5x) | False |
| 466 | poppin_party | 心絵 (Cover) | 95.2 | 190.0 | 0.501 | half(0.5x) | False |
| 344 | pastel_palettes | Y.O.L.O！！！！！(パスパレver.) | 105.3 | 210.0 | 0.501 | half(0.5x) | False |
| 340 | pastel_palettes | With〜きみとわたしたちの物語〜 | 93.7 | 187.0 | 0.501 | half(0.5x) | False |
| 121 | hello_happy_world | はれやか すこやか ぴかりんりん♪ | 115.4 | 230.0 | 0.502 | half(0.5x) | False |
| 613 | roselia | Fear Nothing | 115.4 | 230.0 | 0.502 | half(0.5x) | True |
| 84 | ave_mujica | Ave Mujica | 113.2 | 222.0 | 0.510 | half(0.5x) | True |
| 269 | mygo | 迷路日々 | 133.3 | 260.0 | 0.513 | half(0.5x) | True |
| 74 | ave_mujica | Imprisoned XII | 105.3 | 158.0 | 0.666 |  | False |
| 536 | raise_a_suilen | Drown Out the Noise and Push Through the Trash | 127.7 | 190.0 | 0.672 |  | True |
| 439 | poppin_party | 青春 To Be Continued | 193.5 | 134.0 | 1.444 |  | True |
| 565 | raise_a_suilen | 狂乱 Hey Kids!! (Cover) | 272.7 | 142.0 | 1.921 | double(2x) | True |
| 572 | roselia | Opera of the wasteland | 260.9 | 135.0 | 1.932 | double(2x) | True |
| 300 | mygo | 春日影 | 187.5 | 97.0 | 1.933 | double(2x) | True |
| 449 | poppin_party | チョコレイトの低音レシピ | 187.5 | 96.0 | 1.953 | double(2x) | True |
| 638 | roselia | 悪魔の子 (Cover) | 176.5 | 90.0 | 1.961 | double(2x) | True |
| 281 | mygo | 過惰幻 | 166.7 | 85.0 | 1.961 | double(2x) | False |
| 496 | raise_a_suilen | Takin’ my Heart | 181.8 | 92.0 | 1.976 | double(2x) | False |
| 267 | mygo | 春日影 (MyGO!!!!! ver.) | 193.5 | 97.0 | 1.995 | double(2x) | False |
| 146 | hello_happy_world | やっほー！いっぽ！わんだふぉー！ | 315.8 | 158.0 | 1.999 | double(2x) | True |
| 345 | pastel_palettes | 奏（かなで） (Cover) | 150.0 | 75.0 | 2.000 | double(2x) | False |
| 71 | afterglow | I love your way！ | 260.9 | 130.0 | 2.007 | double(2x) | False |
| 545 | raise_a_suilen | Embrace of light | 153.8 | 76.0 | 2.024 | double(2x) | False |
| 586 | roselia | Avant-garde HISTORY | 230.8 | 114.0 | 2.024 | double(2x) | False |
| 118 | hello_happy_world | せかいのっびのびトレジャー！ | 193.5 | 85.0 | 2.277 |  | False |