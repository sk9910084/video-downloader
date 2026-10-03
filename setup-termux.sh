#!/bin/bash
# Video Downloader — Termux one-command setup
# Use: curl -sL https://sk9910084.github.io/video-downloader/setup-termux.sh | bash
set -e
echo "== Video Downloader setup =="
pkg update -y
pkg install -y python ffmpeg git
pip install -U yt-dlp
if [ ! -d "$HOME/video-downloader" ]; then
  git clone https://github.com/sk9910084/video-downloader "$HOME/video-downloader"
else
  cd "$HOME/video-downloader" && git pull --quiet || true
fi
cd "$HOME/video-downloader/backend"
echo ""
echo "Setup ho gaya! Server start ho raha hai…"
echo "Chrome me kholo: http://localhost:8080"
echo "(Band karne ke liye: VolumeDown + C)"
python server.py
