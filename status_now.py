import os, pickle, requests, re
os.chdir('/opt/yt-automation')

# Load env
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

import googleapiclient.discovery
from google.auth.transport.requests import Request

def get_service(token_file):
    with open(token_file, 'rb') as f:
        creds = pickle.load(f)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

channels = [
    ('Smart Money Daily',  'UC9k4fEX_Kg5ncM1E5rEiE3A', 'youtube_token_ch1.json', '\U0001f4b0'),
    ('AI Advantage Daily', 'UCwXkcGaQFoYcR64KuOYhgbA', 'youtube_token_ch2.json', '\U0001f916'),
]

lines = ['\U0001f4ca <b>Current Status Report</b>', '']
total_views_all  = 0
total_shorts_all = 0

for name, ch_id, token, emoji in channels:
    svc = get_service(token)

    ch    = svc.channels().list(part='statistics,contentDetails', id=ch_id).execute()
    stats = ch['items'][0]['statistics']
    subs      = int(stats.get('subscriberCount', 0))
    vid_count = int(stats.get('videoCount', 0))
    uploads_pl = ch['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Get all video IDs
    video_ids = []
    page_token = None
    while True:
        kwargs = dict(part='snippet', playlistId=uploads_pl, maxResults=50)
        if page_token:
            kwargs['pageToken'] = page_token
        pl = svc.playlistItems().list(**kwargs).execute()
        for item in pl.get('items', []):
            video_ids.append(item['snippet']['resourceId']['videoId'])
        page_token = pl.get('nextPageToken')
        if not page_token:
            break

    regular_views = 0
    shorts_views  = 0
    top_videos    = []

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        vresp = svc.videos().list(part='statistics,contentDetails,snippet', id=','.join(batch)).execute()
        for item in vresp.get('items', []):
            title    = item['snippet']['title']
            views    = int(item['statistics'].get('viewCount', 0))
            duration = item['contentDetails'].get('duration', 'PT0S')
            m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
            total_sec = sum(int(x or 0)*mul for x, mul in zip(m.groups(), [3600, 60, 1])) if m else 999
            is_short  = total_sec <= 60
            if is_short:
                shorts_views += views
            else:
                regular_views += views
            if views > 0:
                top_videos.append((views, is_short, title))

    top_videos.sort(reverse=True)
    total_views_all  += regular_views
    total_shorts_all += shorts_views

    lines.append(f'{emoji} <b>{name}</b>')
    lines.append(f'  \U0001f441 <b>{regular_views:,}</b> video views  |  \u26a1 <b>{shorts_views:,}</b> shorts views')
    lines.append(f'  \U0001f465 {subs:,} subscribers  |  \U0001f4f9 {vid_count} videos')
    if top_videos:
        lines.append('  Top performing:')
        for v, is_s, t in top_videos[:3]:
            tag = '\u26a1' if is_s else '\U0001f4fa'
            lines.append(f'    {tag} {t[:45]} \u2014 {v:,} views')
    lines.append('')

lines.append(f'\U0001f30e <b>Combined: {total_views_all + total_shorts_all:,} total views</b>')
lines.append(f'  Videos: {total_views_all:,}  |  Shorts: {total_shorts_all:,}')

msg = '\n'.join(lines)
print(msg)

tg_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
chat_id  = os.environ.get('TELEGRAM_CHAT_ID', '')
r = requests.post(
    f'https://api.telegram.org/bot{tg_token}/sendMessage',
    json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'HTML'},
    timeout=10,
)
print('Telegram:', r.status_code)
