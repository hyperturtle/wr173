from bottle import Bottle, run, static_file, request, redirect, response
import os
from pymongo import Connection
from bson import ObjectId
import markdown
from functools import wraps
import pbkdf2
import requests
import re
import json
from bs4 import BeautifulSoup
import random
import string
import yaml
import datetime
import hashlib
from jinja2 import Environment, FileSystemLoader
from time import time

jinjaenv = Environment(loader=FileSystemLoader('templates'))

app = Bottle()

MONGOLAB_URI         = os.environ.get('MONGOLAB_URI', 'MONGOLAB_URI goes here')
CONNECTION           = Connection(MONGOLAB_URI)
db                   = CONNECTION[MONGOLAB_URI.rsplit('/',1)[1]]
COOKIE_KEY           = "random characacters go here"
COOKIE_NAME          = 'pick a cookie name'
SESSION_CUTOFF       = 60*60*24 #timeout expiration
BROWSER_ID_AUDIENCES = ['hostnames','that','will', 'be', 'used', 'against', 'browserid', 'auth']


def bad(msg="Error"):
    return dict(status="error", msg=msg)


def good(**kwargs):
    return dict(status="good",**kwargs)


def user_required(f):
    @wraps(f)
    def df(*args, **kwargs):
        if not request.environ['auth']:
            return bad("Not logged in")
        else:
            return f(*args, **kwargs)
    return df


def cookier(n=None):
    response.set_cookie(COOKIE_NAME, n,
        secret=COOKIE_KEY,
        path='/',
        httponly=True)


def unicodecleaner(txt):
    try:
        txt = txt.decode('utf-8', 'ignore')
    except UnicodeDecodeError:
        pass
    except UnicodeEncodeError:
        pass
    
    txt = txt.encode('ascii', 'ignore')
    return txt


def generate_session(length=50):
    return ''.join(random.choice(string.ascii_letters + string.digits) for x in range(length))


def render_idea(idea):
    doc = idea['doc'] if 'doc' in idea else ''
    ret = []

    meta = {}
    meta['title'] = idea['txt']

    section = doc.strip().split('\n\n',1)
    if len(section) == 2:
        newmeta, content = section
        newmeta = yaml.load(newmeta)
        if newmeta:
            meta.update()
    else:
        content = section[0]

    ret.append('<h1>' + meta['title'] + '</h1>')

    if 'date' in meta:
        ret.append('<h2>' + meta['date'] + '</h2>')

    ret.append(markdown.markdown(content,
        extensions=['fenced_code', 'codehilite']))

    return ''.join(ret)


@app.hook('before_request')
def before_request():
    auth_cookie = request.get_cookie(COOKIE_NAME, secret=COOKIE_KEY)
    session = db.sessions.find_one({"session_id": auth_cookie})

    if auth_cookie and session:
        request.environ['auth'] = True
        request.environ['auth.email'] = session['email']
        db.sessions.update({'_id': session['_id']}, {'$set': {'atime': time()}}, safe=True)
    else:
        request.environ['auth'] = False
        request.environ['auth.email'] = ''

    db.sessions.remove({'atime': {'$lt': SESSION_CUTOFF}})


@app.get('/')
def index():
    #idea = db.ideas.find_one({'_id': ObjectId('xxxxxxxxxxxxxxxxxxxxxxxxx')})
    idea = "yay it worked!"
    return jinjaenv.get_template('index.html').render(intro="")


@app.get('/styles.css')
def styles():
    return static_file('styles.css', root=os.path.dirname(__file__))


@app.get('/script.js')
def script():
    return static_file('script.js', root=os.path.dirname(__file__)) 


@app.get('/favicon.ico')
def favicon():
    return static_file('favicon.ico', root=os.path.dirname(__file__))


@app.get('/robots.txt')
def robots():
    response.content_type = 'text/plain; charset=utf-8'
    return "User-agent: *\nAllow: /\n"


@app.get('/idea')
@user_required
def get_ideas():
    ideas = db.ideas.find({'email':request.environ['auth.email']}, sort=[('mtime',1)])
    def myfilter(x):
        return dict(
            txt=x['txt'],
            id=str(x['_id']),
            wc=x['wc'] if 'wc' in x else 0,
            published=x['published'])
    ret = map(myfilter, ideas)
    return good(ideas=list(ret))


@app.get('/idea/<idea_id>')
def get_idea(idea_id):
    idea = db.ideas.find_one(dict(
        _id=ObjectId(idea_id),
        email=request.environ['auth.email']))

    idea =  db.ideas.find_one({'$or': [
          {'_id': ObjectId(idea_id), 'email': request.environ['auth.email'] },
          {'_id': ObjectId(idea_id), 'published': 1 }
        ]})

    
    if 'published' not in idea:
        idea['published'] = 0

    if idea:
        doc = idea['doc'] if 'doc' in idea else ''
        return good(id=str(idea['_id']), txt=idea['txt'], doc=doc, published=idea['published'], wc=idea['wc'] if 'wc' in idea else 0)
    return bad()


@app.post('/idea')
@user_required
def add_idea():
    txt  = request.forms.get('txt')
    date = datetime.datetime.now().strftime("%Y/%m/%d")
    doc  = "type: post\ndate: {1}\n\n...".format(txt, date)
    wc   = 0
    md5  = hashlib.md5()
    try:
        httpr = requests.get(txt.split('#')[0])
        soup  = BeautifulSoup(httpr.text)
        title = ''.join(soup.title.stripped_strings)
        title = title.encode('utf-8', 'ignore')
        doc   = "type: link\ndate: {2}\n\n[{0}]({1})".format(title, txt, date)
        wc    = len(doc.split())
        txt   = title
    except Exception as e:
        pass

    md5.update(unicodecleaner(txt))
    md5.update(unicodecleaner(doc))
    md5.update(str(0))

    new_id = db.ideas.insert(dict(
        txt=txt,
        doc=doc,
        wc=wc,
        published=0,
        email=request.environ['auth.email'],
        mtime=time(),
        hash=md5.hexdigest()
        ))
    return good(id=str(new_id), txt=txt)


@app.put('/idea/<idea_id>')
@user_required
def update_idea(idea_id):
    idea = db.ideas.find_one(dict(
        _id=ObjectId(idea_id),
        email=request.environ['auth.email']))

    if not idea:
        return bad()

    txt       = request.forms['txt'] if 'txt' in request.forms else idea['txt']
    doc       = request.forms['doc'] if 'doc' in request.forms else idea['doc']
    published = int(request.forms['published']) if 'published' in request.forms else idea['published']
    md5       = hashlib.md5()
    wordcount = len(doc.split())

    if txt is not None:
        if not txt:
            txt = "untitled"

    md5.update(unicodecleaner(txt))
    md5.update(unicodecleaner(doc))
    md5.update(str(published))
    hsh = md5.hexdigest()

    if hsh != idea['hash']:
        db.ideas.update(dict(_id=ObjectId(idea_id)), {"$set": dict(
            txt=txt,
            doc=doc,
            wc=wordcount,
            published=published,
            mtime=time(),
            hash=hsh
            )})

    return good()


@app.delete('/idea/<idea_id>')
@user_required
def delete_idea(idea_id):
    db.ideas.remove(ObjectId(idea_id))
    return good()


@app.get('/<idea_id>.<format>')
@app.get('/<idea_id>')
def get_md_idea_html(idea_id, format='html'):
    idea = db.ideas.find_one({'$or': [
          {'_id': ObjectId(idea_id), 'email': request.environ['auth.email'] },
          {'_id': ObjectId(idea_id), 'published': 1 }
        ]})

    if not idea: return bad()

    #return ''.join(ret)
    return jinjaenv.get_template('base.html').render(content=render_idea(idea))



@app.post('/auth')
def authbrowserid():
    assertion = request.forms['assertion']

    for audience in BROWSER_ID_AUDIENCES:
        payload = dict(assertion=assertion, audience=audience)
        r       = requests.post('https://browserid.org/verify', data=payload)
        data    = json.loads(r.content) if r else None

        if data and data['status'] == 'okay':
            email = data['email']
            session_id = generate_session()
            db.sessions.insert(dict(email=email, session_id=session_id, atime=time()))
            cookier(session_id)
            return redirect('/')

    return redirect('/')


@app.get('/auth')
def getauth():
    if request.environ['auth']:
        return good(email=request.environ['auth.email'])
    return bad()


@app.get('/logout')
@app.post('/logout')
def logout():
    response.delete_cookie("auth")
    db.sessions.remove({"email": request.environ['auth.email']})
    return redirect('/')


if __name__ == '__main__':
    run(app, reloader=True, host='0.0.0.0', port=9999)
