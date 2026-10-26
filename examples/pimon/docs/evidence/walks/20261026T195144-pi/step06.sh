[ -f /etc/pimon/pimon.toml ] || sudo cp /opt/pimon/current/pimon.toml.example /etc/pimon/pimon.toml
cd /opt/pimon/current
python3 -m pimon check-config --config /etc/pimon/pimon.toml
