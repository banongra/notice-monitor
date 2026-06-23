import feedparser
import json
import os

rss_url = "https://news.google.com/rss/search?q=배터리&hl=ko&gl=KR&ceid=KR:ko"
save_file = "seen_posts.json"

feed = feedparser.parse(rss_url)

# 기존에 본 글 목록 불러오기
if os.path.exists(save_file):
    with open(save_file, "r", encoding="utf-8") as f:
        seen_posts = json.load(f)
else:
    seen_posts = []

new_posts = []

for entry in feed.entries[:10]:
    post_id = entry.link

    if post_id not in seen_posts:
        new_posts.append({
            "title": entry.title,
            "link": entry.link,
            "published": entry.get("published", "날짜 없음")
        })
        seen_posts.append(post_id)

# 새 글 출력
if new_posts:
    print(f"새 글 {len(new_posts)}개 발견!")
    print("-" * 50)

    for post in new_posts:
        print("제목:", post["title"])
        print("링크:", post["link"])
        print("날짜:", post["published"])
        print("-" * 50)
else:
    print("새 글이 없습니다.")

# 본 글 목록 저장
with open(save_file, "w", encoding="utf-8") as f:
    json.dump(seen_posts, f, ensure_ascii=False, indent=2)