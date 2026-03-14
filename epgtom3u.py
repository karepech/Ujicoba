import requests
from datetime import datetime, timedelta

def generate_m3u_from_sportsdb(event_ids, stream_url, nama_channel):
    print('#EXTM3U name="🔴 BAKUL WIFI VIP EVENTS"')
    
    for event_id in event_ids:
        try:
            # Ambil data dari API
            api_call = requests.get(f"https://www.thesportsdb.com/api/v1/json/123/lookupevent.php?id={event_id}", timeout=10)
            storage = api_call.json()
            
            if storage and storage.get("events"):
                event = storage["events"][0]
                
                # Ambil detail pertandingan
                date_event = event.get("dateEvent")
                time_event = event.get("strTime", "00:00:00")
                home_team = event.get("strHomeTeam")
                away_team = event.get("strAwayTeam")
                league = event.get("strLeague", "Sports")
                
                # Konversi waktu dari UTC ke WIB (+7 Jam)
                waktu_utc = datetime.strptime(f"{date_event} {time_event}", "%Y-%m-%d %H:%M:%S")
                waktu_wib = waktu_utc + timedelta(hours=7)
                jam_tayang = waktu_wib.strftime("%H:%M")
                
                # FORMAT JUDUL: Waktu - Match [Nama Channel]
                judul_m3u = f"{jam_tayang} WIB - {home_team} vs {away_team} ({league}) [{nama_channel}]"
                
                # Cetak ke format M3U
                print(f'#EXTINF:-1 group-title="{league}", {judul_m3u}')
                print(stream_url)
                
        except Exception as e:
            print(f"Gagal memproses Event ID {event_id}: {e}")

# --- EKSEKUSI ---
# Contoh ID event, URL streaming, dan Nama Channel
daftar_event = [2052711, 2052712]
url_streaming = "https://bwifi.my.id/live_event_1.m3u8"
nama_channel_tv = "Event Channel 1"

generate_m3u_from_sportsdb(daftar_event, url_streaming, nama_channel_tv)
