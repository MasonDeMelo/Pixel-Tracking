# tracking.py

import base64
import datetime
import configparser
import sys

import urllib.parse

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

config = configparser.ConfigParser()
config.read('./config.ini')

engine = create_engine(config["Database"]["url"])
Session = sessionmaker(bind=engine)

from flask import Flask, Response, request, render_template, redirect
app = Flask(__name__)

from celery import Celery
celery = Celery(app.name, broker=config["RabbitMQ"]["url"])

#Routes

@app.route("/")
def index():
    session = Session()
    pixels = session.query(Pixel).all()
    for pixel in pixels:
        pixel.obfuscated_id = obfuscate(pixel.id)
    return render_template("index.html", pixels=pixels) 

@app.route("/pixel.gif")
def pixel():
    timestamp = datetime.datetime.now()
    pixelId = deobfuscate(request.args.get("id"))
    userAgent = request.headers["User-Agent"]
    remoteAddr = request.headers.getlist("X-Forwarded-For")[0]

    save_pixel_hit.delay(pixelId, timestamp, userAgent, remoteAddr)

    pixel = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7".encode())
    return Response(pixel, mimetype="image/gif")

@app.route("/pixel", methods=["GET", "POST"])
def new_pixel():
    if request.method == "POST":
        name = request.form.get('pixel_name')
        try:
            newPixel = create_new_pixel(name)
            obfuscatedId = obfuscate(newPixel.id)
            return redirect("/pixel/" + obfuscatedId)
        except:
            return Response("Could not create new pixel.")
    else:
        return render_template("new.html")

@app.route("/pixel/<obfuscatedId>")
def pixel_info(obfuscatedId=None):
    deobfuscatedId = deobfuscate(obfuscatedId)
    if (deobfuscatedId is None):
        return Response("That's not a real pixel.")
    else:
        session = Session()
        pixel = session.query(Pixel).get(deobfuscatedId)
        session.commit()
        if (pixel is None):
            return Response("Pixel: " + str(deobfuscatedId) + " does not exist.")
        else:
            pixel_url = build_pixel_url(pixel.id)
            return render_template("pixel.html", pixel=pixel, pixel_url=pixel_url)
    
def obfuscate(id):
    return None if (id is None) else base64.b64encode(str(id).encode('ascii')).decode()

def deobfuscate(obfuscatedId):
    try:
        return None if (obfuscatedId is None) else int(base64.b64decode(bytes(obfuscatedId.encode())).decode())
    except:
        return None

def build_pixel_url(id):
    url = list(urllib.parse.urlparse(config['PixelTracker']['host']))
    url[2] = "pixel.gif"
    url[4] = urllib.parse.urlencode({'id': obfuscate(id)})
    return urllib.parse.urlunparse(url)

# Tasks

@celery.task
def save_pixel_hit(pixelId, timestamp, userAgent, remoteAddr):
    session = Session()
    newPixelHit = PixelHit(pixelId=pixelId, timestamp=timestamp, userAgent=userAgent, remoteAddr=remoteAddr)
    session.add(newPixelHit)
    session.commit()
    return newPixelHit

@celery.task
def create_new_pixel(name):
    session = Session()
    newPixel = Pixel(name=name)
    session.add(newPixel)
    session.commit()
    return newPixel

# DB Models
Base = declarative_base()

class Pixel(Base):
    __tablename__ = 'pixel'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    hits = relationship("PixelHit", back_populates="pixel")

    def __repr(self):
        return ("<Pixel(id='%d', name='%s'" % self.id, self.name)

class PixelHit(Base):
    __tablename__ = 'pixel_hits'

    id = Column(Integer, primary_key=True)
    pixel = relationship("Pixel", back_populates="hits")
    pixelId = Column(Integer, ForeignKey('pixel.id'))
    timestamp = Column(String)
    userAgent = Column(String)
    remoteAddr = Column(String)

    def __repr__(self):
        return ("<PixelHit(id='%d', pixelId='%d', timestamp='%s', user-agent='%s', remote-address='%s'>"
                % (self.id
                  ,self.pixelId
                  ,self.timestamp
                  ,self.userAgent
                  ,self.remoteAddr))


# Main
if __name__ == "__main__":
    app.run(debug=True)
