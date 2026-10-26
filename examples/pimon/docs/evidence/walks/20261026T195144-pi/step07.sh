sudo cp /opt/pimon/current/deploy/pimon.service /etc/systemd/system/pimon.service
sudo systemctl daemon-reload
sudo systemctl enable --now pimon
