import requests
from bs4 import BeautifulSoup
import re

url = "http://infocom.ssu.ac.kr/kor/notice/undergraduate.php"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers, timeout=15)
response.encoding = response.apparent_encoding

html = response.text

print("상태 코드:", response.status_code)
print("인코딩:", response.encoding)
print("HTML 길이:", len(html))
print("-" * 80)

target = "2026년도 하반기 AI보안연구센터 학부생 인턴 모집"

if target in html:
    print("✅ HTML 안에서 목표 공지 제목을 찾았습니다.")
else:
    print("❌ HTML 안에서 목표 공지 제목을 못 찾았습니다.")

print("-" * 80)

soup = BeautifulSoup(html, "html.parser")
text = soup.get_text("\n", strip=True)

if target in text:
    print("✅ 화면 텍스트 안에서 목표 공지 제목을 찾았습니다.")
else:
    print("❌ 화면 텍스트 안에서도 목표 공지 제목을 못 찾았습니다.")

print("-" * 80)
print("AI보안 / 인턴 / 2026. 05. 28 키워드 포함 줄 찾기")
print("-" * 80)

lines = text.split("\n")

for line in lines:
    line = re.sub(r"\s+", " ", line).strip()

    if "AI보안" in line or "인턴" in line or "2026. 05. 28" in line or "2026.05.28" in line:
        print(line)

print("-" * 80)
print("날짜가 들어간 줄 30개 출력")
print("-" * 80)

count = 0

for line in lines:
    line = re.sub(r"\s+", " ", line).strip()

    if re.search(r"20\d{2}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}", line):
        print(line)
        count += 1

    if count >= 30:
        break