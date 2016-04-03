steadycache
--------------

`steadycache` is an easy-to-use Python library for caching function outputs, with a focus on caching multiprocessed calls to slow, rate-limited web APIs.

Now you can cache those pesky slow API responses in your app, or do expensive calculations less frequently with just a single decorator!

You'll need a Redis server available to store your cache in, and the python Redis library installed. All instances of your app connecting to the same Redis server will use the same cache.

That means that if you have access to an expensive API call which you want to update only once per `n` seconds across multiple processes or your cluster, you can just set `expires=n` in the function call you want to rate-limit, and updating the cache with a new value will happen just once across all instances using the same cache.

Be careful! New arguments mean a new, unique cache entry, as a function with different input isn't expected to have the same output. This means`cached_function(1)` and `cached_function(2)` will have results relevant to the arguments. Naturally, this implies that the function code will be run twice.

Finally, if you're running something for which it's important to respond right away, and it isn't important to be totally up-to-date, you can update the cache in the background, while returning the old results with the option `bg_cache=True`. This is great for web applications running on Flask, web.py, and similar frameworks.

Any function that has JSON-serializable arguments and JSON-serializable output (some JSON-serializable types are: strings, dictionaries, lists, numerical types, and None) can be cached in the following way:

```
import StrictRedis
import steadycache.cache
redis_conn = redis.StrictRedis('redis-server-hostname.example.com', PORT)
cache = steadycache.cache.create_cache(redis_conn)

# Caches for 1 second
@cache(expires=1)
def cached_function(arg):
    return do_slow_work(arg)
```

To ensure fast response times after the first call, enable updating the cache in the background. As explained above, this returns immediately while kicking off a background Python thread to update the value. The background update uses threading, so [beware of GIL lock slowdowns](https://docs.python.org/2/library/threading.html) in CPython if your function blocks on computation and not I/O.

```
@cache(expires=1, bg_caching=True)
def cached_function(arg):
    return do_slow_work(arg)
```

To install, use distutils (`python setup.py install` -- recommended), or just copy the `steadycache` folder into your program.

And that's all you need!

Use `nose` to run the tests, and please report bugs!

