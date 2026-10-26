REL=/opt/pimon/releases/$(date +%Y%m%d-%H%M%S)
sudo mkdir -p "$REL" /etc/pimon
sudo cp -r ~/pimon/pimon ~/pimon/deploy ~/pimon/pimon.toml.example "$REL"/
sudo ln -sfn "$REL" /opt/pimon/current
