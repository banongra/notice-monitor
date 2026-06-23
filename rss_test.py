import feedparser

rss_url = "https://news.google.com/rss/search?q=배터리&hl=ko&gl=KR&ceid=KR:ko"

feed = feedparser.parse(rss_url)

print("사이트 제목:", feed.feed.title)
print("-" * 50)

for entry in feed.entries[:10]:
    print("제목:", entry.title)
    print("링크:", entry.link)
    print("날짜:", entry.published)
    print("-" * 50)