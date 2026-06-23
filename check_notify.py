import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import re
from datetime import datetime


# ==============================
# 1. 설정
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

save_file = "seen_notices_notify.json"

headers = {
    "User-Agent": "Mozilla/5.0"
}

# 여기에 디스코드 웹훅 URL 붙여넣기
DISCORD_WEBHOOK_URL = "https://discordapp.com/api/webhooks/1518853202685067477/RPX_KJs5JwpwIYS8Db0fgJAT_HzN4nj7IST_D48HE6WPFA1LzsiPLVRvpwpG3URS8Baz"


# ==============================
# 2. 공통 함수
# ==============================
def clean_text(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def extract_date(text):
    text = clean_text(text)

    match = re.search(
        r"(20\d{2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\.?",
        text
    )

    if match:
        year = match.group(1)
        month = match.group(2).zfill(2)
        day = match.group(3).zfill(2)
        return f"{year}-{month}-{day}"

    return ""


def is_number_text(text):
    text = clean_text(text)
    return text.isdigit()


def split_same_line_title_date_views(text):
    text = clean_text(text)

    pattern = r"(20\d{2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\.?\s*(\d+)?"
    match = re.search(pattern, text)

    if not match:
        return "", "", ""

    title = clean_text(text[:match.start()])
    date = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    views = match.group(4) if match.group(4) else ""

    return title, date, views


def is_bad_title(title):
    title = clean_text(title)

    if not title:
        return True

    if len(title) < 5:
        return True

    bad_words = [
        "로그인", "회원가입", "사이트맵", "개인정보", "이전", "다음",
        "공지사항", "News", "Q&A", "FAQ", "오시는 길",
        "학부소개", "교수진", "교육", "입학", "졸업",
        "자랑스런 우리학부", "진로 및 산업분야", "진로 및 ㅅ산업분야",
        "학사정보", "교과과정", "대학원", "자료실",
        "전자정보공학부", "숭실대학교", "주메뉴 바로가기",
        "본문 바로가기", "하단 바로가기", "Skip to content",
        "TOP", "HOME", "사이트 바로가기", "검색", "목록",
        "전체", "학부공지", "일반공지", "게시판", "번호", "제목",
        "작성일", "조회수", "첨부파일",
        "학생회", "인스타", "인스타그램", "instagram", "facebook",
        "youtube", "sns", "팔로우"
    ]

    if any(word.lower() in title.lower() for word in bad_words):
        return True

    if title.isdigit():
        return True

    if extract_date(title):
        return True

    if title.startswith("http"):
        return True

    return False


def is_probable_notice_title(text):
    text = clean_text(text)

    if is_bad_title(text):
        return False

    if is_number_text(text):
        return False

    if len(text) < 8:
        return False

    if not re.search(r"[가-힣A-Za-z0-9]", text):
        return False

    return True


def get_response_soup(url):
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    response.encoding = response.apparent_encoding
    return BeautifulSoup(response.text, "html.parser")


def normalize_link(base_url, href):
    if not href:
        return base_url

    href = href.strip()

    if href.startswith("javascript"):
        return base_url

    if href.startswith("#"):
        return base_url

    return urljoin(base_url, href)


def find_link_for_title(soup, base_url, title):
    title_clean = clean_text(title)

    for a in soup.find_all("a"):
        a_text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href")

        if not a_text or not href:
            continue

        if title_clean == a_text:
            return normalize_link(base_url, href)

    for a in soup.find_all("a"):
        a_text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href")

        if not a_text or not href:
            continue

        if title_clean in a_text or a_text in title_clean:
            return normalize_link(base_url, href)

    return base_url


def deduplicate_notices(notices):
    unique = []
    seen = set()

    for notice in notices:
        key = (
            clean_text(notice.get("site", "")),
            clean_text(notice.get("title", "")),
            clean_text(notice.get("date", ""))
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(notice)

    return unique


# ==============================
# 3. DISU 공지 가져오기
# ==============================
def get_disu_notices(site_name, url):
    notices = []

    max_pages = 5

    for page in range(1, max_pages + 1):
        if page == 1:
            page_url = url
        else:
            page_url = f"{url}?page={page}"

        try:
            soup = get_response_soup(page_url)
        except Exception as e:
            print(f"[오류] {site_name} {page}페이지 접속 실패: {e}")
            continue

        rows = soup.find_all("tr")

        for row in rows:
            cols = row.find_all("td")

            if len(cols) < 5:
                continue

            no_text = clean_text(cols[0].get_text())
            category = clean_text(cols[1].get_text())
            title_col = cols[2]
            date = extract_date(clean_text(cols[3].get_text()))
            views = clean_text(cols[4].get_text())

            a = title_col.find("a")
            if not a:
                continue

            title = clean_text(a.get_text(" ", strip=True))
            href = a.get("href")

            if not is_probable_notice_title(title):
                continue

            full_link = normalize_link(page_url, href)
            is_pinned = no_text == "공지"

            notices.append({
                "site": site_name,
                "type": "고정공지" if is_pinned else "일반공지",
                "no": no_text,
                "category": category,
                "title": title,
                "date": date,
                "views": views,
                "link": full_link,
                "id": f"{site_name}_{title}_{date}"
            })

    return deduplicate_notices(notices)[:100]


# ==============================
# 4. 숭실대 전자정보공학부 공지 가져오기
# ==============================
def get_infocom_notices(site_name, url):
    notices = []

    try:
        soup = get_response_soup(url)
    except Exception as e:
        print(f"[오류] {site_name} 접속 실패: {e}")
        return notices

    page_text = soup.get_text("\n", strip=True)

    lines = []
    for line in page_text.split("\n"):
        line = clean_text(line)
        if line:
            lines.append(line)

    for i, line in enumerate(lines):
        date = extract_date(line)

        if not date:
            continue

        title = ""
        views = ""

        same_line_view_match = re.search(
            r"20\d{2}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}\.?\s+(\d+)",
            line
        )

        if same_line_view_match:
            views = same_line_view_match.group(1)

        if not views and i + 1 < len(lines) and is_number_text(lines[i + 1]):
            views = clean_text(lines[i + 1])

        for j in range(i - 1, max(i - 6, -1), -1):
            candidate = clean_text(lines[j])

            if not is_probable_notice_title(candidate):
                continue

            title = candidate
            break

        if not title:
            continue

        link = find_link_for_title(soup, url, title)

        notices.append({
            "site": site_name,
            "type": "일반공지",
            "no": "",
            "category": "",
            "title": title,
            "date": date,
            "views": views,
            "link": link,
            "id": f"{site_name}_{title}_{date}"
        })

    return deduplicate_notices(notices)[:30]


# ==============================
# 5. 사이트별 공지 가져오기
# ==============================
def get_notices(site_name, url):
    if "disu.ac.kr" in url:
        return get_disu_notices(site_name, url)

    if "infocom.ssu.ac.kr" in url:
        return get_infocom_notices(site_name, url)

    return []


# ==============================
# 6. 본 공지 기록 저장/불러오기
# ==============================
def load_seen_notices():
    if os.path.exists(save_file):
        with open(save_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_seen_notices(seen_notices):
    with open(save_file, "w", encoding="utf-8") as f:
        json.dump(seen_notices, f, ensure_ascii=False, indent=2)


# ==============================
# 7. 디스코드 알림
# ==============================
def send_discord_notification(notice):
    if DISCORD_WEBHOOK_URL == "여기에_디스코드_웹훅_URL_붙여넣기":
        print("[알림 생략] 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return

    content = (
        f"📢 **새 공지 발견!**\n\n"
        f"**사이트:** {notice.get('site', '')}\n"
        f"**구분:** {notice.get('type', '')}\n"
        f"**분류:** {notice.get('category', '')}\n"
        f"**제목:** {notice.get('title', '')}\n"
        f"**날짜:** {notice.get('date', '')}\n"
        f"**조회수:** {notice.get('views', '')}\n"
        f"**링크:** {notice.get('link', '')}"
    )

    data = {
        "content": content
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=data, timeout=10)

        if response.status_code in [200, 204]:
            print(f"[알림 전송 완료] {notice.get('title', '')}")
        else:
            print(f"[알림 전송 실패] 상태코드: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"[알림 오류] {e}")


# ==============================
# 8. 전체 확인 실행
# ==============================
def check_all_sites():
    seen_notices = load_seen_notices()

    all_notices = []
    new_notices = []

    for site in sites:
        print(f"[확인 중] {site['name']}")

        notices = get_notices(site["name"], site["url"])
        print(f"가져온 공지 수: {len(notices)}")

        for notice in notices:
            if notice["id"] not in seen_notices:
                new_notices.append(notice)
                seen_notices.append(notice["id"])

            all_notices.append(notice)

    save_seen_notices(seen_notices)

    return all_notices, new_notices


def main():
    print("=" * 60)
    print("공지 확인 시작:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    all_notices, new_notices = check_all_sites()

    print(f"전체 공지 수: {len(all_notices)}")
    print(f"새 공지 수: {len(new_notices)}")

    if new_notices:
        for notice in new_notices:
            print("-" * 60)
            print("사이트:", notice.get("site", ""))
            print("제목:", notice.get("title", ""))
            print("날짜:", notice.get("date", ""))
            print("링크:", notice.get("link", ""))

            send_discord_notification(notice)
    else:
        print("새 공지가 없습니다.")

    print("=" * 60)
    print("공지 확인 종료")
    print("=" * 60)


if __name__ == "__main__":
    main()