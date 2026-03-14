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
# II. LOGIKA PENCOCOKAN 3 LAPIS (ID -> NAMA -> KEMIRIPAN)
# ==========================================
def bersihkan_teks(teks):
    """Membersihkan teks dari simbol untuk mempermudah pencocokan."""
    if not teks: return ""
    return re.sub(r'[^a-z0-9\s]', '', teks.lower()).strip()

def cari_kecocokan_channel(m3u_id, m3u_name, epg_chans):
    """
    Alur pencocokan:
    1. Cocokkan by ID EPG (tvg-id)
    2. Cocokkan by Nama Persis (tvg-name vs display-name)
    3. Cocokkan by Kemiripan (Minimal 2 kata berurutan sama)
    """
    # 1. Cek berdasarkan ID (Jika tvg-id tersedia di M3U)
    if m3u_id and m3u_id in epg_chans:
        return m3u_id

    m3u_nama_bersih = bersihkan_teks(m3u_name)
    if not m3u_nama_bersih: return None
    
    m3u_kata = m3u_nama_bersih.split()

    # 2. Cek berdasarkan Nama Persis
    for cid, cname in epg_chans.items():
        if m3u_nama_bersih == bersihkan_teks(cname):
            return cid

    # 3. Cek Kemiripan Kata Berurutan (Minimal 2 kata berurutan)
    kandidat_terbaik = None
    max_berurutan = 0

    for cid, cname in epg_chans.items():
        cname_kata = bersihkan_teks(cname).split()
        
        # Hitung seberapa banyak kata berurutan yang sama persis
        skor_berurutan = 0
        for i in range(len(m3u_kata)):
            for j in range(len(cname_kata)):
                k = 0
                while (i + k < len(m3u_kata) and 
                       j + k < len(cname_kata) and 
                       m3u_kata[i+k] == cname_kata[j+k]):
                    k += 1
                if k > skor_berurutan:
                    skor_berurutan = k
        
        # Syarat: Minimal 2 kata berurutan sama (Contoh: "Bein Sports" cocok dengan "Bein Sports 1 HD")
        # Atau 1 kata jika nama channel memang cuma 1 kata (Contoh: "Spotv")
        syarat_minimal = 2 if len(m3u_kata) > 1 else 1
        
        if skor_berurutan >= syarat_minimal and skor_berurutan > max_berurutan:
            max_berurutan = skor_berurutan
            kandidat_terbaik = cid

    return kandidat_terbaik

# ==========================================
# III. FUNGSI UNDUH (PARALEL)
# ==========================================
def fetch_url(url, is_xml=False):
    try:
        r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        if is_xml:
            return gzip.decompress(r.content) if r.content[:2] == b'\x1f\x8b' else r.content
        return r.text
    except Exception as e:
        print(f"Gagal mengunduh {url}: {e}")
        return None

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
    limit_date = now_wib + timedelta(days=3)
    
    epg_chans = {}
    epg_logos = {}
    jadwal_events = {} # Format: {channel_id: [{title, start, stop, logo}]}

    # 1. Unduh EPG Paralel untuk menghemat waktu
    print("Step 1: Mengunduh dan memproses EPG secara paralel...")
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
                if not st or not sp or sp <= now_wib or st >= limit_date: continue 
                
                title = pg.findtext("title") or ""
                prog_logo = pg.find("icon").get("src") if pg.find("icon") is not None else ""
                
                if cid not in jadwal_events: jadwal_events[cid] = []
                jadwal_events[cid].append({
                    "title": title, "start": st, "stop": sp, "logo": prog_logo,
                    "is_live": (st - timedelta(minutes=5)) <= now_wib < sp
                })
        except Exception as e:
            print(f"Error parsing XML: {e}")

    # 2. Unduh dan Jahit M3U Paralel
    print("Step 2: Menjahit jadwal ke M3U menggunakan logika pencocokan 3 Lapis...")
    hasil_m3u_akhir = []
    
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
                    if any(t.upper().startswith("#EXTINF") for t in block):
                        block = [] 
                block.append(ln_clean) 
            else:
                stream_url = ln_clean
                extinf_idx = next((i for i, t in enumerate(block) if t.upper().startswith("#EXTINF")), -1)
                
                if extinf_idx != -1:
                    raw_extinf = block[extinf_idx]
                    
                    # Ekstrak Info dari baris M3U
                    tvg_id_match = re.search(r'(?i)tvg-id=["\']([^"\']*)["\']', raw_extinf)
                    m3u_id = tvg_id_match.group(1) if tvg_id_match else ""
                    
                    if "," in raw_extinf:
                        raw_attrs, m3u_name = raw_extinf.split(",", 1)
                        m3u_name = m3u_name.strip()
                    else:
                        m3u_name = "Unknown Channel"
                        raw_attrs = raw_extinf

                    # Eksekusi Pencocokan 3 Lapis
                    matched_cid = cari_kecocokan_channel(m3u_id, m3u_name, epg_chans)

                    clean_attr = re.sub(r'(?i)\s*(group-title|tvg-id|tvg-logo|tvg-name)=["\'][^"\']*["\']', '', raw_attrs).strip()
                    if not clean_attr.upper().startswith("#EXTINF"):
                        clean_attr = "#EXTINF:-1 " + clean_attr.replace('#EXTINF:-1', '').replace('#EXTINF:0', '').strip()

                    # Jika ada jadwal untuk channel ini, buatkan daftarnya di playlist
                    if matched_cid and matched_cid in jadwal_events:
                        for ev in jadwal_events[matched_cid]:
                            jam = f"{ev['start'].strftime('%H:%M')}-{ev['stop'].strftime('%H:%M')} WIB"
                            final_logo = ev['logo'] if ev['logo'] else epg_logos.get(matched_cid, "")
                            
                            if ev['is_live']:
                                judul = f"🔴 {jam} - {ev['title']} [{m3u_name}]"
                                extinf_final = f'{clean_attr} group-title="🔴 SEDANG TAYANG" tvg-id="{matched_cid}" tvg-logo="{final_logo}", {judul}'
                            else:
                                lbl_hari = ""
                                if ev['start'].date() == now_wib.date() + timedelta(days=1): lbl_hari = "Besok "
                                elif ev['start'].date() > now_wib.date() + timedelta(days=1): lbl_hari = f"{ev['start'].strftime('%d/%m')} "
                                
                                judul = f"⏳ {lbl_hari}{jam} - {ev['title']} [{m3u_name}]"
                                extinf_final = f'{clean_attr} group-title="📅 AKAN TAYANG" tvg-id="{matched_cid}" tvg-logo="{final_logo}", {judul}'

                            # Masukkan SEMUA jadwal tanpa batasan 3 server
                            hasil_m3u_akhir.append({
                                "sort_time": ev['start'].timestamp(),
                                "is_live": ev['is_live'],
                                "data": [extinf_final, stream_url]
                            })
                block = []

    print("Step 3: Merender Playlist Akhir...")
    # Urutkan: Live di atas, disusul upcoming berdasarkan waktu tayang
    hasil_m3u_akhir.sort(key=lambda x: (not x["is_live"], x["sort_time"]))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U url-tvg="{GLOBAL_EPG_URL}" name="🔴 BAKUL WIFI SPORTS ALL"\n')
        if not hasil_m3u_akhir: 
            f.write(f'#EXTINF:-1 group-title="ℹ️ INFO", BELUM ADA JADWAL\n{LINK_STANDBY}\n')
        for item in hasil_m3u_akhir: 
            f.write("\n".join(item["data"]) + "\n")

    print(f"Selesai! {len(hasil_m3u_akhir)} jadwal berhasil dipetakan ke playlist.")

if __name__ == "__main__": 
    main()
