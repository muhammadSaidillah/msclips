# Demo MSclips Maker di komputer kamu

Dari video mentah sampai klip 9:16 yang siap diunduh. Semua jalan di komputer kamu dengan **satu perintah**.

## Sekali saja: persiapan

1. **Pasang Docker Desktop** dari https://www.docker.com/products/docker-desktop/ (Windows / Mac), lalu buka aplikasinya
   sampai tulisannya "Docker Desktop is running".
2. **Unduh kode MSclips Maker**: buka https://github.com/muhammadSaidillah/msclips, klik tombol hijau **Code** →
   **Download ZIP**, lalu ekstrak (misalnya ke folder `Documents/msclips`).
3. **Kunci Claude API** (untuk AI yang memilih potongan terbaik):
   - Buat kunci di https://console.anthropic.com → API Keys.
   - Di folder `msclips` tadi, buat file teks bernama persis `.env` (tanpa nama depan) berisi satu baris:
     ```
     ANTHROPIC_API_KEY=isi-kunci-kamu-di-sini
     ```
   - Kunci ini hanya ada di komputer kamu. Jangan kirim kunci ke siapa pun, termasuk lewat chat.

## Menjalankan

1. Buka **Terminal** (Mac) atau **PowerShell** (Windows) di folder `msclips`.
   - Mac: klik kanan folder → *New Terminal at Folder*.
   - Windows: buka folder, ketik `powershell` di address bar, tekan Enter.
2. Jalankan:
   ```
   docker compose up --build
   ```
   Pertama kali butuh sekitar 5–10 menit untuk menyiapkan semuanya. Berikutnya cukup beberapa detik.
3. Kalau sudah muncul tulisan `Uvicorn running on http://0.0.0.0:8000`, buka **http://localhost:3000** di browser.

## Alur demo

1. **New Project** → seret video mentah (MP4/MOV, sampai 20 GB). Tunggu status **Ready**.
2. Di halaman project, bagian **Find the best clips with AI**:
   pilih **jumlah klip**, **panjang klip** (15–30, 30–60, atau 45–90 detik) dan **bahasa** (Indonesia/English/Auto),
   lalu klik **Analyse**.
   - Analisis pertama mengunduh model transkripsi (±500 MB), jadi lebih lama.
   - Progress yang tampil adalah progress sungguhan: transkripsi lalu analisis AI.
3. Muncul daftar **kandidat klip** dengan skor, hook, dan alasan. Klik **Preview** untuk memutar potongannya,
   **Reject** untuk membuang.
4. Centang klip yang mau dibuat, pilih **gaya editing** (default **Auto: best style per clip**, atau pilih salah satu
   gaya dari skill kamu / showcase Before-After), lalu klik **Render**.
5. Klip jadi muncul di **Rendered clips**: putar langsung, lihat laporan QC, **Download MP4**, atau
   **Download all as ZIP**.

## Mematikan

Tekan `Ctrl + C` di Terminal. Data project tetap tersimpan untuk demo berikutnya.
Untuk menghapus semua data demo: `docker compose down -v`.

## Kalau ada kendala

- **"Cannot reach the MSclips Maker API"**: Terminal masih menyiapkan atau sudah ditutup. Tunggu tulisan
  `Uvicorn running`, atau jalankan lagi `docker compose up`.
- **Analisis berhenti dengan pesan soal API key**: file `.env` belum ada atau salah nama. Perbaiki, lalu jalankan ulang
  `docker compose up`. Transkrip yang sudah dibuat tidak hilang.
- **Windows menyimpan file sebagai `.env.txt`**: di Notepad pilih *Save as type: All files* lalu beri nama `.env`.
- **Port sudah dipakai**: tutup aplikasi lain yang memakai port 3000 atau 8000.

Gunakan hanya video yang kamu punya haknya.
