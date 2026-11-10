# MomongaPet (Windows)

작업표시줄 위를 돌아다니는 작은 데스크톱 펫. 맥 버전([namgiju/MomongaPet](https://github.com/namgiju/MomongaPet))을 윈도우용으로 옮긴 거예요.

- 작업표시줄 위를 걷고, 가만히 있고, 가끔 낮잠을 자요
- 잡아서 끌면 대롱대롱 흔들리고, 던지면 날아가서 떨어져요
- 맨 앞 창 위로 뛰어올라가 그 위에서 놀아요 (창을 움직이면 떨어지고, 창이 가려지거나 닫혀도 떨어짐)
- 3분 동안 컴퓨터를 안 쓰면 잠들고, 다시 쓰면 깨요
- 게임·영상을 전체화면으로 띄우면 숨었다가, 나가면 다시 나타나요

## 실행

```bat
pip install -r requirements.txt
run.bat
```

오류를 확인하려면 `python momongapet.py`로 실행하세요 (콘솔에 오류가 보여요).

## 사용법

| 동작 | 결과 |
|---|---|
| 드래그 | 잡아서 옮기기, 놓으면 던지기 |
| 더블클릭 | 점프 |
| 클릭 (자는 중) | 깨우기 |
| 우클릭 | 메뉴 (스프라이트 폴더 열기 / 다시 불러오기 / 재우기 / 윈도우 시작 시 자동 실행 / 종료) |

## 스프라이트 넣기

`sprites/` 폴더(또는 `%USERPROFILE%\MomongaPet\sprites`, 이쪽이 우선)에 PNG를 넣고 우클릭 → **스프라이트 다시 불러오기**.

파일 이름 규칙: `상태_번호.png` (예: `idle_01.png`, `idle_02.png`)

| 상태 | 언제 | 없으면 |
|---|---|---|
| `idle` | 가만히 있을 때 | 흰 동그라미 |
| `walk` | 걸을 때 | idle |
| `drag` | 잡혀 있을 때 | idle |
| `jump` | 뛰어오를 때 (한 번만 재생) | fall → idle |
| `fall` | 떨어질 때 | idle |
| `sleep` | 잘 때 | idle |
| `dizzy` | 떨어지거나 던져진 뒤 2초 (스스로 뛴 점프는 제외) | idle |
| `notice` | 새 창이 뜨거나, 창 위에서 마우스가 움직이면 "!" (4칸 고정 순서: idle왼쪽·idle오른쪽·walk왼쪽·walk오른쪽) | idle |
| `watchright` / `watchleft` | "!" 뒤 마우스 쪽을 내려다봄. 2초간 움직임 없으면 평소대로 (뒤집지 않음) | idle |

원본 그림은 오른쪽을 보고 있어야 해요 (왼쪽으로 걸을 땐 자동으로 뒤집힘).

### 그린스크린 시트 자르기

초록 배경에 캐릭터가 가로로 나란히 있는 이미지를 프레임별 투명 PNG로 잘라줘요. 시트 전체의 바닥을 기준으로 맞춰서 점프처럼 위아래로 움직이는 동작도 그대로 살아나요.

```bat
python tools\slice_sprites.py sheet.png idle      &rem -> sprites\idle_01.png ...
```

## 설정

크기, 속도, 잠드는 시간, 점프 확률 등은 `momongapet.py` 맨 위에 있어요.

## exe로 만들기

```bat
build.bat        &rem -> dist\MomongaPet.exe (Python 없이 실행되는 파일 하나, 약 46MB)
```

`sprites\` 폴더의 그림이 exe 안에 기본 스프라이트로 들어가요. 아이콘은 `icon.png`가 있으면 그걸, 없으면 `sprites\idle_01.png`로 만들어요.

`캐릭터 바꾸기 프롬프트.txt`(친구가 GPT로 자기 캐릭터를 만들 때 쓰는 안내)도 `dist`에 같이 복사돼요. 완성본은 [Releases](https://github.com/namgiju/MomongaPet-Win/releases)에서 받을 수 있어요.

서명이 없는 exe라서 **스마트 앱 컨트롤**이 켜진 PC에서는 실행이 막혀요 (Windows 보안 → 앱 및 브라우저 컨트롤). 그런 PC에서는 `run.bat`으로 실행하세요.
