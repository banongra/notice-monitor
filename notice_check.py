import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import re
import csv
from datetime import datetime


# ==============================
# 1. 확인할 사이트 목록
# ==============================
sites = [
    {
        "name": "숭실대 전자정보공학부 학부공지",
        "url": "http://infocom.ssu.ac.kr/kor/notice/undergraduate.php"
    },
    {
        "name": "차세대반도체 혁신융합대학 공지사항",
        "url": "https://www.disu.ac.kr/community/notice"
    }
]


# ==============================
# 2. 저장 파일 설정
# ==============================
save_file = "seen_notices.json"   # 이미 본 공지 저장
csv_file = "notices.csv"          # 새 공지 누적 저장


headers = {
    "User-Agent": "Mozilla/5.0"
}


# ==============================
# 3. 텍스트 정리 함수
# ==============================
def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


def extract_date(text):
    match = re.search(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}", text)
    if match:
        return match.group()
    return "날짜 없음"


# ==============================
# 4. 공지 가져오기 함수
# ==============================
def get_notices(site_name, url):
    notices = []

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"[오류] {site_name} 접속 실패:", e)
        return notices

    soup = BeautifulSoup(response.text, "html.parser")

    # =================================================
    # DISU 공지사항 전용 처리
    # 표 구조:
    # No. | 분류 | 제목 | 날짜 | 조회수
    # =================================================
    if "disu.ac.kr" in url:
        rows = soup.find_all("tr")

        for row in rows:
            cols = row.find_all("td")

            if len(cols) < 5:
                continue

            no_text = clean_text(cols[0].get_text())
            category = clean_text(cols[1].get_text())
            title_col = cols[2]
            date = clean_text(cols[3].get_text())
            views = clean_text(cols[4].get_text())

            a = title_col.find("a")
            if not a:
                continue

            title = clean_text(a.get_text())
            href = a.get("href")

            if not title or not href:
                continue

            full_link = urljoin(url, href)
            is_pinned = no_text == "공지"

            notices.append({
                "site": site_name,
                "no": no_text,
                "category": category,
                "title": title,
                "link": full_link,
                "date": date,
                "views": views,
                "pinned": is_pinned,
                "id": full_link
            })

        return notices[:30]

    # =================================================
    # 숭실대 전자정보공학부 공지사항 처리
    # 일반적인 링크 기반 처리
    # =================================================
    links = soup.find_all("a")

    for a in links:
        title = clean_text(a.get_text())
        href = a.get("href")

        if not title or not href:
            continue

        # 너무 짧은 메뉴명, 숫자, 페이지 번호 제외
        if len(title) < 8:
            continue

        skip_words = [
            "로그인", "회원가입", "사이트맵", "개인정보", "이전", "다음",
            "공지사항", "News", "Q&A", "FAQ", "오시는 길",
            "학부소개", "교수진", "교육", "연구", "입학", "졸업"
        ]

        if any(word in title for word in skip_words):
            continue

        full_link = urljoin(url, href)

        # 게시글 링크처럼 보이는 것만 수집
        if (
            "idx=" not in full_link
            and "board" not in full_link
            and "notice" not in full_link
            and "undergraduate" not in full_link
        ):
            continue

        parent_text = clean_text(a.parent.get_text(" ", strip=True))
        date = extract_date(parent_text)

        notices.append({
            "site": site_name,
            "no": "",
            "category": "",
            "title": title,
            "link": full_link,
            "date": date,
            "views": "",
            "pinned": False,
            "id": full_link
        })

    # 중복 제거
    unique_notices = []
    seen_links = set()

    for notice in notices:
        if notice["link"] not in seen_links:
            unique_notices.append(notice)
            seen_links.add(notice["link"])

    return unique_notices[:30]


# ==============================
# 5. 새 공지를 CSV에 저장하는 함수
# ==============================
def save_new_notices_to_csv(new_notices):
    file_exists = os.path.exists(csv_file)

    with open(csv_file, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow([
                "발견시간",
                "사이트",
                "구분",
                "분류",
                "번호",
                "제목",
                "날짜",
                "조회수",
                "링크"
            ])

        for notice in new_notices:
            pinned_text = "고정공지" if notice.get("pinned") else "일반공지"

            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                notice.get("site", ""),
                pinned_text,
                notice.get("category", ""),
                notice.get("no", ""),
                notice.get("title", ""),
                notice.get("date", ""),
                notice.get("views", ""),
                notice.get("link", "")
            ])


# ==============================
# 6. 기존에 본 공지 불러오기
# ==============================
if os.path.exists(save_file):
    with open(save_file, "r", encoding="utf-8") as f:
        seen_notices = json.load(f)
else:
    seen_notices = []


# ==============================
# 7. 사이트별 공지 확인
# ==============================
new_notices = []

for site in sites:
    print(f"\n[{site['name']}] 확인 중...")

    notices = get_notices(site["name"], site["url"])

    print(f"가져온 공지 수: {len(notices)}")

    for notice in notices:
        if notice["id"] not in seen_notices:
            new_notices.append(notice)
            seen_notices.append(notice["id"])


# ==============================
# 8. 결과 출력 및 저장
# ==============================
if new_notices:
    print("\n==============================")
    print(f"새 공지 {len(new_notices)}개 발견!")
    print("==============================")

    for notice in new_notices:
        pinned_text = "고정공지" if notice.get("pinned") else "일반공지"

        print("사이트:", notice.get("site", ""))
        print("구분:", pinned_text)
        print("분류:", notice.get("category", ""))
        print("번호:", notice.get("no", ""))
        print("제목:", notice.get("title", ""))
        print("날짜:", notice.get("date", ""))
        print("조회수:", notice.get("views", ""))
        print("링크:", notice.get("link", ""))
        print("-" * 50)

    save_new_notices_to_csv(new_notices)
    print(f"\nCSV 저장 완료: {csv_file}")

else:
    print("\n새 공지가 없습니다.")


# ==============================
# 9. 본 공지 목록 저장
# ==============================
with open(save_file, "w", encoding="utf-8") as f:
    json.dump(seen_notices, f, ensure_ascii=False, indent=2)