#!/bin/bash

echo "**** Package up custom_code *****"
tar -czvf eye.tar --exclude=__pycache__ -C custom_components eyeonwater/
echo "**** Push code to Jarvis *****"
scp eye.tar jarvis:/opt/docker/home-assistant/home-assistant/config/custom_components/.
echo "**** Unpack code *****"
ssh jarvis "docker exec -i home-assistant tar -xvf /config/custom_components/eye.tar -C /config/custom_components/"
echo "**** Clear pycache *****"
ssh jarvis "docker exec -i home-assistant rm -Rf /config/custom_components/eyeonwater/__pycache__/"
echo "**** Restart Home Assistant *****"
ssh jarvis "docker restart home-assistant"
echo "**** Push complete *****"