# INDI Control Panel

## What is it?
I put this together to be able to remotely control some of the functions I would normally access via KStars+Ekos. Basically, my workflow was using KStars and Ekos on my Mac to remotely control my mount, via INDI server running on a Raspberry Pi. I'm a big fan of the simplicity + ease of use of INDI Web Manager, and I wanted something like that to initiate imaging, as well as check the status of an imaging job. I am figuring this out as I go along, but I suspect the new workflow would be to polar align, choose a target, and then instead of needing to keep KStars open at all times, I could just start imaging from my smartphone.

## How do I install it?
Clone or download this github repository
```	
git clone https://github.com/novakeith/INDI-Control-Panel.git
```

Ensure you have Flask for Python installed. I created a virtual environment to keep things simple. Enter the working directory where you put the project files and create the venv:
```	
python3 -m venv . 
./bin/pip3 install flask
```

Please also make sure gunicorn, flask-socketio, and eventlet are all installed
```
./bin/pip3 install gunicorn
./bin/pip3 install flask-socketio
./bin/pip3 install eventlet
```

You don't need the virtual environment if you want to install flask system wide, it's your choice. Either way, when you are ready, you should make launch.sh executable and run the service with:
```	
chmod +x launch.sh
./launch.sh
```


## What's the current status?
I'm figuring out how to make this work. I'm not sure if it will go anywhere. Right now, you can:
- run this, either locally or on your remote observatory PC/Raspberry Pi;
- access the service via http://127.0.0.1:5000 if you are local or http://{Your-Remote-Computer-IP}:5000
- you can currently get the status of your INDI devices, with live refresh from your INDI server
- 

## What's the roadmap?
I want to add:
- enable remote control of your CCD and download images to a local directory. (or save on the remote server)
- have the server initiate an imaging job 
- have the server manage that imaging job 
- get the current status of your imaging job, with the option to pause + pick back up at another time if needed
- save the parameters of that imaging job, to save you time in the future (ie. KStars calls this an imaging sequence; maybe you like taking 200 lights, 25 darks, 25 biases, and 25 flats every time)
- configure where imaging jobs are saved
- figure out how to download images if the server is running remotely, maybe this would be in a batch manner when the job is complete
- Once the above is complete I think I can look at adding other functionality

## Anything else I need to know?
I'm very rusty at all this, so I did use generative AI to assist (Gemini 2.5 Pro).
