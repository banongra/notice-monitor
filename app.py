import streamlit as st
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
import os
import re
import csv
import pandas as pd
from datetime import datetime


# ==============================
# 1. 기본 설정
# ==============================
st.set_page_config(
    page_title="공지 모니터링",
    page_icon="📢",
    layout="wide"
)

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

save_file = "seen_notices.json"
csv_file = "notices.csv"

headers = {
    "User-Agent": "Mozilla/5.0"
}


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


def split_same_line_title_date_views(text):
    """
    한 줄에 제목/날짜/조회수가 같이 들어온 경우 분리.
    예:
    제목 2026. 05. 28 730
    """
    text = clean_text(text)

    pattern = r"(20\d{2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})\.?\s*(\d+)?"
    match = re.search(pattern, text)

    if not match:
        return "", "", ""

    title = clean_text(text[:match.start()])
    date = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
    views = match.group(4) if match.group(4) else ""

    return title, date, views


def is_number_text(text):
    text = clean_text(text)
    return text.isdigit()

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

    # 한글, 영어, 숫자 중 하나라도 포함되어야 제목으로 인정
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
    """
    제목과 가장 유사한 a 태그를 찾아서 링크 연결.
    못 찾으면 목록 페이지 URL 반환.
    """
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


# ==============================
# 3. DISU 공지사항 가져오기
# ==============================
def get_disu_notices(site_name, url):
    notices = []

    # 확인할 DISU 페이지 수
    # page=1은 기본 공지 페이지와 동일하게 취급
    max_pages = 6

    for page in range(1, max_pages + 1):
        if page == 1:
            page_url = url
        else:
            page_url = f"{url}?page={page}"

        try:
            soup = get_response_soup(page_url)
        except Exception as e:
            st.error(f"[오류] {site_name} {page}페이지 접속 실패: {e}")
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

    # 여러 페이지를 돌면 고정공지가 페이지마다 반복될 수 있어서 중복 제거 필수
    return deduplicate_notices(notices)[:100]
# ==============================
# 4. 숭실대 전자정보공학부 학부공지 가져오기
# ==============================
def get_infocom_notices(site_name, url):
    notices = []

    try:
        soup = get_response_soup(url)
    except Exception as e:
        st.error(f"[오류] {site_name} 접속 실패: {e}")
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

        # 날짜 줄 자체에 조회수가 붙은 경우
        same_line_view_match = re.search(
            r"20\d{2}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2}\.?\s+(\d+)",
            line
        )

        if same_line_view_match:
            views = same_line_view_match.group(1)

        # 날짜 다음 줄이 숫자면 조회수로 판단
        if not views and i + 1 < len(lines) and is_number_text(lines[i + 1]):
            views = clean_text(lines[i + 1])

        # 핵심: 날짜 바로 위쪽에서 제목 찾기
        # 너무 멀리 올라가면 학생회 인스타 같은 엉뚱한 항목이 잡히므로 5줄까지만 탐색
        for j in range(i - 1, max(i - 6, -1), -1):
            candidate = clean_text(lines[j])

            if not is_probable_notice_title(candidate):
                continue

            # 제목 후보가 너무 메뉴성인 경우 제외
            if candidate in ["학부공지", "일반공지", "전체", "검색", "목록"]:
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
# 5. 중복 제거
# ==============================
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
# 6. 사이트별 분기
# ==============================
def get_notices(site_name, url):
    if "disu.ac.kr" in url:
        return get_disu_notices(site_name, url)

    if "infocom.ssu.ac.kr" in url:
        return get_infocom_notices(site_name, url)

    return []


# ==============================
# 7. 저장 관련 함수
# ==============================
def load_seen_notices():
    if os.path.exists(save_file):
        with open(save_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_seen_notices(seen_notices):
    with open(save_file, "w", encoding="utf-8") as f:
        json.dump(seen_notices, f, ensure_ascii=False, indent=2)


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
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                notice.get("site", ""),
                notice.get("type", ""),
                notice.get("category", ""),
                notice.get("no", ""),
                notice.get("title", ""),
                notice.get("date", ""),
                notice.get("views", ""),
                notice.get("link", "")
            ])


def check_all_sites():
    seen_notices = load_seen_notices()

    all_notices = []
    new_notices = []

    for site in sites:
        notices = get_notices(site["name"], site["url"])

        for notice in notices:
            notice["checked_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if notice["id"] not in seen_notices:
                notice["status"] = "NEW"
                new_notices.append(notice)
                seen_notices.append(notice["id"])
            else:
                notice["status"] = "기존"

            all_notices.append(notice)

    save_seen_notices(seen_notices)

    if new_notices:
        save_new_notices_to_csv(new_notices)

    return all_notices, new_notices


def load_saved_csv():
    if os.path.exists(csv_file):
        return pd.read_csv(csv_file)
    return pd.DataFrame()


# ==============================
# 8. 화면 구성
# ==============================
st.title("📢 공지 모니터링 대시보드")

st.write("등록한 웹사이트에서 새 공지가 올라왔는지 확인하는 대시보드입니다.")

with st.sidebar:
    st.header("등록된 사이트")

    for site in sites:
        st.markdown(f"- [{site['name']}]({site['url']})")

    st.divider()

    st.caption("저장 파일")
    st.code(save_file)
    st.code(csv_file)

    reset_seen = st.button("본 공지 기록 초기화")

    if reset_seen:
        if os.path.exists(save_file):
            os.remove(save_file)
        st.success("본 공지 기록을 초기화했습니다.")

    reset_csv = st.button("누적 CSV 삭제")

    if reset_csv:
        if os.path.exists(csv_file):
            os.remove(csv_file)
        st.success("누적 CSV를 삭제했습니다.")


col1, col2, col3 = st.columns(3)

with col1:
    check_button = st.button("🔍 지금 공지 확인하기", use_container_width=True)

with col2:
    st.metric("등록 사이트 수", len(sites))

with col3:
    if os.path.exists(csv_file):
        saved_count = len(pd.read_csv(csv_file))
    else:
        saved_count = 0
    st.metric("누적 저장 공지 수", saved_count)


st.divider()


if check_button:
    with st.spinner("공지 확인 중..."):
        all_notices, new_notices = check_all_sites()

    st.subheader("확인 결과")

    if new_notices:
        st.success(f"새 공지 {len(new_notices)}개 발견!")

        for notice in new_notices:
            with st.container(border=True):
                if notice["type"] == "고정공지":
                    st.markdown("📌 **고정공지**")
                else:
                    st.markdown("🆕 **새 공지**")

                st.markdown(f"### [{notice['title']}]({notice['link']})")
                st.write(f"사이트: {notice['site']}")
                st.write(f"분류: {notice.get('category', '')}")
                st.write(f"번호: {notice.get('no', '')}")
                st.write(f"날짜: {notice.get('date', '')}")
                st.write(f"조회수: {notice.get('views', '')}")

    else:
        st.info("새 공지가 없습니다.")

    st.subheader("이번에 확인한 전체 공지")

    if all_notices:
        df_all = pd.DataFrame(all_notices)

        df_show = df_all[[
            "status",
            "site",
            "type",
            "category",
            "no",
            "title",
            "date",
            "views",
            "link"
        ]]

        st.dataframe(
            df_show,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("가져온 공지가 없습니다. 사이트 구조가 바뀌었거나 접속이 막혔을 수 있습니다.")


st.divider()

st.subheader("누적 저장된 새 공지")

saved_df = load_saved_csv()

if not saved_df.empty:
    st.dataframe(
        saved_df,
        use_container_width=True,
        hide_index=True
    )

    csv_data = saved_df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label="CSV 다운로드",
        data=csv_data,
        file_name="notices.csv",
        mime="text/csv"
    )
else:
    st.caption("아직 저장된 새 공지가 없습니다.")