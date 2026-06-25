import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import re
from datetime import datetime


# ==============================
# 1. 설정~~~
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

# GitHub Actions Secret에서 불러옴
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")


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


def get_response_soup(url):
    response = requests.get(url, headers=headers, timeout=15)
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

    # 1차: 완전 일치
    for a in soup.find_all("a"):
        a_text = clean_text(a.get_text(" ", strip=True))
        href = a.get("href")

        if not a_text or not href:
            continue

        if title_clean == a_text:
            return normalize_link(base_url, href)

    # 2차: 부분 일치
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


def is_probable_notice_title(text):
    text = clean_text(text)

    if not text:
        return False

    if len(text) < 5:
        return False

    if text.isdigit():
        return False

    if extract_date(text):
        return False

    if text.startswith("http"):
        return False

    # 메뉴/푸터/SNS 계열만 최소한으로 제외
    bad_words = [
        "로그인", "회원가입", "사이트맵", "개인정보",
        "주메뉴 바로가기", "본문 바로가기", "하단 바로가기",
        "학생회", "인스타", "인스타그램", "instagram",
        "facebook", "youtube", "sns", "팔로우",
        "이전", "다음", "검색", "목록", "닫기"
    ]

    if any(word.lower() in text.lower() for word in bad_words):
        return False

    if not re.search(r"[가-힣A-Za-z0-9]", text):
        return False

    return True


# ==============================
# 3. DISU 공지 가져오기
# ==============================
def get_disu_notices(site_name, url):
    notices = []

    # DISU는 여러 페이지 확인
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

            # No. | 분류 | 제목 | 날짜 | 조회수
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

    # ==============================
    # 1. 실제 공지 목록 시작점 찾기
    # 구조 예:
    # 총 게시물
    # 790
    # [전자공학전공] 반도체공정교육 최종 선발자 명단 안내
    # 2026. 06. 24
    # 87
    # ==============================
    start_index = None

    for i, line in enumerate(lines):
        if line == "총 게시물":
            start_index = i + 2
            break

    if start_index is None:
        print("[경고] '총 게시물' 위치를 찾지 못했습니다.")
        return notices

    # ==============================
    # 2. 제목 / 날짜 / 조회수 구조로 읽기
    # ==============================
    i = start_index

    while i < len(lines) - 1:
        title = clean_text(lines[i])

        # 게시판 목록 끝으로 보이면 중단
        if title in ["이전", "다음", "처음", "마지막", "검색", "목록"]:
            break

        # 제목 다음 줄이 날짜인지 확인
        date = extract_date(lines[i + 1])

        if not date:
            i += 1
            continue

        views = ""

        # 날짜 다음 줄이 숫자면 조회수
        if i + 2 < len(lines) and is_number_text(lines[i + 2]):
            views = clean_text(lines[i + 2])
            next_i = i + 3
        else:
            next_i = i + 2

        # 단어 기반 bad_title 사용하지 않음
        if len(title) >= 5 and not extract_date(title) and not title.isdigit():
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

        i = next_i

    return deduplicate_notices(notices)[:50]


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
    if not DISCORD_WEBHOOK_URL:
        print("[알림 생략] 디스코드 웹훅 URL이 설정되지 않았습니다.")
        return False

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
            return True

        print(f"[알림 전송 실패] 상태코드: {response.status_code}")
        print(response.text)
        return False

    except Exception as e:
        print(f"[알림 오류] {e}")
        return False


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

        print("가져온 공지 목록:")
        for idx, notice in enumerate(notices, start=1):
            print(
                f"{idx}. [{notice.get('date', '')}] "
                f"{notice.get('title', '')} "
                f"/ id={notice.get('id', '')}"
            )

        for notice in notices:
            if notice["id"] not in seen_notices:
                new_notices.append(notice)

            all_notices.append(notice)

    return all_notices, new_notices, seen_notices


def main():
    print("=" * 60)
    print("공지 확인 시작:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    all_notices, new_notices, seen_notices = check_all_sites()

    print(f"전체 공지 수: {len(all_notices)}")
    print(f"새 공지 수: {len(new_notices)}")

    if new_notices:
        for notice in new_notices:
            print("-" * 60)
            print("사이트:", notice.get("site", ""))
            print("제목:", notice.get("title", ""))
            print("날짜:", notice.get("date", ""))
            print("링크:", notice.get("link", ""))

            sent = send_discord_notification(notice)

            # 알림 전송 성공했을 때만 seen 목록에 저장
            # 이렇게 해야 알림 실패 시 다음 실행에서 다시 시도함
            if sent:
                seen_notices.append(notice["id"])
    else:
        print("새 공지가 없습니다.")

    save_seen_notices(seen_notices)

    print("=" * 60)
    print("공지 확인 종료")
    print("=" * 60)


if __name__ == "__main__":
    main()