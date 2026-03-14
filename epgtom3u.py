import requests, re, gzip
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import concurrent.futures

# ==========================================
# I. KONFIGURASI SUMBER
# ==========================================
EPG_URLS = [
    "https://raw.githubusercontent.com/AqFad2811/epg/main/indonesia.xml",                    
    "https://raw.githubusercontent.com/AqFad2811/epg/refs/heads/main/astro.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_ALL_SPORTS.xml.gz"                    
]

M3U_URLS = [
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/sports_combined.m3u",
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/event_combined.m3u",
    "https://raw.githubusercontent.com/karepech/Karepetv/refs/heads/main/indonesia_combined.m3u"
]

GLOBAL_EPG_URL = "https://www.open-epg.com/generate/bXxbrwUThe.xml,https://i.mjh.nz/SamsungTVPlus/all.xml,https://i.mjh.nz/au/all/epg.xml,https://www.tdtchannels.com/epg/TV.xml,https://www.open-epg.com/files/indonesia2.xml,https://www.open-epg.com/files/indonesia6.xml,https://www.open-epg.com/files/thailand.xml,https://www.open-epg.com/files/thailandpremium.xml,https://i.mjh.nz/PlutoTV/all.xml,https://www.open-epg.com/files/francepremium.xml,https://avkb.short.gy/tsepg.xml.gz,https://raw.githubusercontent.com/dbghelp/mewatch-EPG/refs/heads/main/mewatch.xml,https://epg1.168.us.kg/mytvsuper.com.xml"

OUTPUT_FILE = "live_matches_all.m3u"
LINK_STANDBY = "https://bwifi.my.id/live.mp4" 

# ==========================================
# II. LOGIKA PENCOCOKAN & ATURAN BENUA
# ==========================================
def bersihkan_teks(teks):
    if not teks: return ""
    return re.sub(r'[^a-z0-9\s]', '', teks.lower()).strip()

def is_valid_time(start_dt, title):
    """Aturan Benua: Memblokir siaran ulang berdasarkan Jam Tayang Benua."""
    w = start_dt.hour + (start_dt.minute / 60.0)
    t = title.lower()

    if any(k in t for k in ['badminton', 'bwf', 'thomas', 'uber', 'sudirman', 'yonex', 'open', 'masters', 'tour', 'motogp', 'moto2', 'moto3', 'f1', 'formula', 'grand prix', 'sprint']): return True
    if any(k in t for k in ['premier', 'champions', 'serie a', 'la liga', 'bundesliga', 'ligue 1', 'fa cup', 'eredivisie', 'uefa', 'euro', 'carabao', 'copa del rey']): 
        if 6.0 <= w <= 16.5: return False 
        return True
    if any(k in t for k in ['mls', 'major league', 'concacaf', 'libertadores', 'sudamericana', 'liga mx', 'brasileiro', 'nba', 'nfl']): 
        if 13.0 <= w <= 23.0: return False 
        return True
    if any(k in t for k in ['saudi', 'roshn', 'caf', 'africa']): 
        if 7.0 <= w <= 19.0: return False 
        return True
    if any(k in t for k in ['j-league', 'k-league', 'afc', 'asian', 'aff', 'liga 1', 'bri liga', 'indonesia', 'timnas', 'piala presiden']): 
        if w < 13.0 or w > 23.5: return False 
        return True
    return True

def cari_kecocokan_channel(m3u_id, m3u_name, epg_chans):
    """Pencocokan 3 Lapis: ID -> Nama -> Kemiripan"""
    if m3u_id and m3u_id in epg_chans: return m3u_id
    m3u_nama_bersih = bersihkan_teks(m3u_name)
    if not m3u_nama_bersih: return None
    m3u_kata = m3u_nama_bersih.split()

    for cid, cname in epg_chans.items():
        if m3u_nama_bersih == bersihkan_teks(cname): return cid

    kandidat_terbaik = None
    max_berurutan = 0
    for cid, cname in epg_chans.items():
        cname_kata = bersihkan_teks(cname).split()
        skor_berurutan = 0
        for i in range(len(m3u_kata)):
            for j in range(len(cname_kata)):
                k = 0
                while (i + k < len(m3u_kata) and j + k < len(cname_kata) and m3u_kata[i+k] == cname_kata[j+k]):
                    k += 1
                if k > skor_berurutan: skor_berurutan = k
        syarat_minimal = 2 if len(m3u_kata) > 1 else 1
        if skor_berurutan >= syarat_minimal and skor_berurutan > max_berurutan:
            max_berurutan = skor_berurutan
            kandidat_terbaik = cid
    return kandidat_terbaik

# ==========================================
# III. FUNGSI UNDUH & CHECKER URL (PARALEL)
# ==========================================
def fetch_url(url, is_xml=False):
    try:
        r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        if is_xml: return gzip.decompress(r.content) if r.content[:2] == b'\x1f\x8b' else r.content
        return r.text
    except Exception: return None

def cek_status_link(url):
    """Mengecek apakah stream IPTV hidup atau mati (Timeout sangat singkat)."""
    try:
        r = requests.get(url, stream=True, timeout=4, headers={'User-Agent': 'VLC/3.0.16'})
        status = r.status_code == 200
        r.close()
        return url, status
    except Exception:
        return url, False

def parse_time(ts):
    if not ts: return None
    try:
        if len(ts) >= 19 and ('+' in ts or '-' in ts):
            dt = datetime.strptime(ts[:20].strip(), "%Y%m%d%H%M%S %z")
            return dt.astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
        return datetime.strptime(ts[:14], "%Y%m%d%H%M%S") + timedelta(hours=7)
    except: return None

# ==========================================
# IV. PROSES UTAMA
# ==========================================
def main():
    now_wib = datetime.utcnow() + timedelta(hours=7)
    # BATAS JADWAL: Maksimal 3 Hari Ke Depan
    limit_date = now_wib + timedelta(days=3)
    
    epg_chans, epg_logos, jadwal_events = {}, {}, {}

    print(f"Step 1: Mengunduh EPG (Batas Jadwal Maksimal: {limit_date.strftime('%d-%m-%Y %H:%M')} WIB)...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        hasil_epg = list(executor.map(lambda url: fetch_url(url, is_xml=True), EPG_URLS))

    for konten in hasil_epg:
        if not konten: continue
        try:
            root = ET.fromstring(konten)
            for ch in root.findall("channel"):
                cid, cn = ch.get("id"), ch.findtext("display-name")
                if cid and cn: 
                    epg_chans[cid] = cn.strip()
                    icon = ch.find("icon")
                    if icon is not None: epg_logos[cid] = icon.get("src")
                    
            for pg in root.findall("programme"):
                cid = pg.get("channel")
                if cid not in epg_chans: continue
                
                st, sp = parse_time(pg.get("start")), parse_time(pg.get("stop"))
                # Filter ketat: Buang EPG masa lalu, dan buang yang lebih dari 3 hari!
                if not st or not sp or sp <= now_wib or st >= limit_date: continue 
                
                title = pg.findtext("title") or ""
                if not is_valid_time(st, title): continue 
                
                prog_logo = pg.find("icon").get("src") if pg.find("icon") is not None else ""
                
                if cid not in jadwal_events: jadwal_events[cid] = []
                jadwal_events[cid].append({
                    "title": title, "start": st, "stop": sp, "logo": prog_logo,
                    "is_live": (st - timedelta(minutes=5)) <= now_wib < sp
                })
        except Exception: pass

    print("Step 2: Menjahit jadwal ke M3U dan Menyiapkan Keranjang Unik...")
    keranjang_unik = {}
    url_perlu_dicek = set()
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        hasil_m3u_raw = list(executor.map(lambda url: fetch_url(url, is_xml=False), M3U_URLS))

    for m3u_text in hasil_m3u_raw:
        if not m3u_text: continue
        lines = m3u_text.splitlines()
        
        block = []
        for ln in lines:
            ln_clean = ln.strip()
            if not ln_clean or "EXTM3U" in ln_clean.upper(): continue
            
            if ln_clean.startswith("#"):
                if ln_clean.upper().startswith("#EXTINF"):
                    if any(t.upper().startswith("#EXTINF") for t in block): block = [] 
                block.append(ln_clean) 
            else:
                stream_url = ln_clean
                extinf_idx = next((i for i, t in enumerate(block) if t.upper().startswith("#EXTINF")), -1)
                
                if extinf_idx != -1:
                    raw_extinf = block[extinf_idx]
                    tvg_id_match = re.search(r'(?i)tvg-id=["\']([^"\']*)["\']', raw_extinf)
                    m3u_id = tvg_id_match.group(1) if tvg_id_match else ""
                    
                    if "," in raw_extinf:
                        raw_attrs, m3u_name = raw_extinf.split(",", 1)
                        m3u_name = m3u_name.strip()
                    else:
                        m3u_name, raw_attrs = "Unknown Channel", raw_extinf

                    matched_cid = cari_kecocokan_channel(m3u_id, m3u_name, epg_chans)
                    clean_attr = re.sub(r'(?i)\s*(group-title|tvg-id|tvg-logo|tvg-name)=["\'][^"\']*["\']', '', raw_attrs).strip()
                    if not clean_attr.upper().startswith("#EXTINF"):
                        clean_attr = "#EXTINF:-1 " + clean_attr.replace('#EXTINF:-1', '').replace('#EXTINF:0', '').strip()

                    if matched_cid and matched_cid in jadwal_events:
                        for ev in jadwal_events[matched_cid]:
                            judul_norm = bersihkan_teks(ev['title'])
                            event_key = f"{judul_norm}_{ev['start'].timestamp()}"

                            if event_key not in keranjang_unik:
                                keranjang_unik[event_key] = {
                                    "title": ev['title'], "start": ev['start'], "stop": ev['stop'],
                                    "is_live": ev['is_live'], "logo": ev['logo'] if ev['logo'] else epg_logos.get(matched_cid, ""),
                                    "streams": [] 
                                }
                            
                            keranjang_unik[event_key]["streams"].append({
                                "clean_attr": clean_attr, "url": stream_url, "m3u_name": m3u_name, "matched_cid": matched_cid
                            })
                            
                            # Jika jadwal mulai dalam 1 JAM (3600 detik) atau sedang Live, masukkan URL ke antrean pengecekan
                            time_to_start = (ev['start'] - now_wib).total_seconds()
                            if time_to_start <= 3600:
                                url_perlu_dicek.add(stream_url)
                block = []

    print(f"Step 3: Memeriksa {len(url_perlu_dicek)} Link yang sedang/akan tayang dalam 1 Jam...")
    status_url_aktif = {}
    if url_perlu_dicek:
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            hasil_cek = executor.map(cek_status_link, url_perlu_dicek)
            for url, is_active in hasil_cek:
                status_url_aktif[url] = is_active

    print("Step 4: Merender Playlist Akhir dengan Indikator Backup...")
    hasil_m3u_akhir = []
    
    for event_key, data in keranjang_unik.items():
        time_to_start = (data['start'] - now_wib).total_seconds()
        valid_streams = []
        
        # Eliminasi Link Mati
        for s in data["streams"]:
            if time_to_start <= 3600:
                # Cek hasil tes, jika True baru dimasukkan
                if status_url_aktif.get(s["url"], False):
                    valid_streams.append(s)
            else:
                # Jadwal besok/lusa otomatis dianggap valid karena server belum menyalakannya
                valid_streams.append(s)
                
        if not valid_streams: continue # Abaikan event jika semua linknya mati saat di-ping
        
        total_link = len(valid_streams)
        utama = valid_streams[0] 
        backup_teks = f" (+{total_link - 1} Backup)" if total_link > 1 else ""
        
        jam = f"{data['start'].strftime('%H:%M')}-{data['stop'].strftime('%H:%M')} WIB"
        
        if data['is_live']:
            judul = f"🔴 {jam} - {data['title']} [{utama['m3u_name']}]{backup_teks}"
            extinf_final = f'{utama["clean_attr"]} group-title="🔴 SEDANG TAYANG" tvg-id="{utama["matched_cid"]}" tvg-logo="{data["logo"]}", {judul}'
        else:
            lbl_hari = ""
            if data['start'].date() == now_wib.date() + timedelta(days=1): lbl_hari = "Besok "
            elif data['start'].date() > now_wib.date() + timedelta(days=1): lbl_hari = f"{data['start'].strftime('%d/%m')} "
            
            judul = f"⏳ {lbl_hari}{jam} - {data['title']} [{utama['m3u_name']}]{backup_teks}"
            extinf_final = f'{utama["clean_attr"]} group-title="📅 AKAN TAYANG" tvg-id="{utama["matched_cid"]}" tvg-logo="{data["logo"]}", {judul}'

        hasil_m3u_akhir.append({
            "sort_time": data['start'].timestamp(),
            "is_live": data['is_live'],
            "data": [extinf_final, utama["url"]]
        })

    hasil_m3u_akhir.sort(key=lambda x: (not x["is_live"], x["sort_time"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U url-tvg="{GLOBAL_EPG_URL}" name="🔴 BAKUL WIFI SPORTS ALL"\n')
        if not hasil_m3u_akhir: 
            f.write(f'#EXTINF:-1 group-title="ℹ️ INFO", BELUM ADA JADWAL\n{LINK_STANDBY}\n')
        for item in hasil_m3u_akhir: 
            f.write("\n".join(item["data"]) + "\n")

    print(f"Selesai! {len(hasil_m3u_akhir)} pertandingan unik dan sehat berhasil dibuat.")

if __name__ == "__main__": 
    main()
