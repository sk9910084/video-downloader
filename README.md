# ⬇ Video Downloader

TikTok, Facebook, Instagram, YouTube aur Kuaishou videos free me download karo.
**100% free, lifetime — koi server kharcha nahi.**

## Kaise kaam karta hai

- **Website** (`index.html`) GitHub Pages par free host hoti hai.
- **Backend** (`backend/server.py`) tumhare **apne phone** par chalta hai (localhost) —
  isliye TikTok/YouTube tumhe block nahi karte aur video seedha tumhare phone me download hoti hai.

## Phone par setup (ek baar, ~10 minute)

1. **F-Droid** app install karo (f-droid.org), usme se **Termux** install karo.
   (Play Store wala Termux purana hai — kaam nahi karega.)
2. Termux kholo, ye ek command paste karo aur Enter dabao:
   ```bash
   curl -sL https://sk9910084.github.io/video-downloader/setup-termux.sh | bash
   ```
3. Sab install hone ke baad Chrome me kholo: **http://localhost:8080**
   Ya website kholo: **https://sk9910084.github.io/video-downloader**

Bas! Ab video ka link paste karo → Dekho dabao → quality chuno → Download karo.

> Note: Termux background me chalta rehna chahiye jab tak download ho raha ho.
> Server band karne ke liye Termux me `VolumeDown + C` dabao.

## Computer par chalana ho to

```bash
pip install yt-dlp
python backend/server.py
# phir browser me: http://localhost:8080
```

## Files

| File | Kaam |
|---|---|
| `index.html` | Website (GitHub Pages + local UI) |
| `backend/server.py` | Localhost backend — yt-dlp se download |
| `setup-termux.sh` | Phone par one-command setup |
