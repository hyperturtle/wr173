#WR137

## Requirements

* Python
* MongoDB

## Installation

Install python modules:

```
pip install -r requirements
```

Configure app.py:

```python
MONGOLAB_URI         = os.environ.get('MONGOLAB_URI', 'MONGOLAB_URI goes here')
CONNECTION           = Connection(MONGOLAB_URI)
db                   = CONNECTION[MONGOLAB_URI.rsplit('/',1)[1]]
COOKIE_KEY           = "random characacters go here"
COOKIE_NAME          = 'pick a cookie name'
SESSION_CUTOFF       = 60*60*24 #timeout expiration
BROWSER_ID_AUDIENCES = ['hostnames','that','will', 'be', 'used', 'against', 'browserid', 'auth']
```
