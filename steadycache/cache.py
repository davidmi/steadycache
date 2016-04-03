# cache.py
# A minimalist caching decorator which json serializes the output of functions
import json
import time
import threading

from functools import wraps
from inspect import getcallargs

class CacheNameClashException(Exception):
    pass

# Though it might make sense to look for name clashes on
# per-cache level, it is conceivable that we might call
# create_cache on the same connection twice, so this
# is a better safeguard against bad habits, even though it's global
decorated = {}

def mangle(fname, f, args, kwargs):
    # We uniquely identify functions by their list of arguments
    # as resolved by the function definition.
    print(fname, f, args, kwargs)
    print(getcallargs)
    print(json.dumps(sorted(getcallargs(f, *args, **kwargs).items(), key=lambda x: x[0])))

    return "@" + fname + "_" + json.dumps(getcallargs(f, *args, **kwargs))


def create_cache(cache_store, prefix=""):
    """
    Creates a caching decorator that connects to the given Redis client
    (or any object similarly supporting get(), set() and lock())

    `cache_store` -- An object supporting get(), set(), and lock()

    `prefix` -- a prefix to append to the keys of the cache entries for the functions decorated
        by the returned decorator. This prevents name clashes between identically-named functions
        in the same module

    Returns -- cache decorator function
    """

    def cache(expires=5, prefix=prefix, bg_caching=False, stale=None):
        """
        Decorator for any function which takes json-serializable arguments and returns json-serializable output
        which caches the results for the given arguments in the given redis database.

        `expires` -- How long to return cached results before calling the underlying function again.
            Defaults to 5 seconds, since permanent caching is rarely what is actually desired.
        `prefix` -- A prefix appended to the cache keys of the decorated function
        `bg_caching` -- Whether to return cached results while results are updated from the underlying function
            in a background thread
        `stale` -- How long old results can be returned when bg_caching is True, so that two calls don't
            try to update the cache in the background. Defaults to 2 * expires
        """
        if not stale:
            stale = 2 * expires

        def decorate(f):
            fname = prefix + "_" + f.__module__ + "_" + f.__name__
            # Prevent two functions in the same program with the same name from
            # accidentally stepping on each others' cache.
            if decorated.get(fname):
                raise CacheNameClashException("A function with the name " + f.__name__ + " has already been cached elsewhere in this module. Please add a prefix to these functions to uniquely identify them")
            decorated[fname] = True

            def update_cache(f, lock, *args, **kwargs):
                try:
                    result = f(*args, **kwargs)
                    cache_store.set(mangle(fname, f, args, kwargs), json.dumps({'timestamp': time.time(), 'result': result}))
                    return result
                finally:
                    lock.release()

            @wraps(f)
            def wrapped(*args, **kwargs):
                cached_result = cache_store.get(mangle(fname, f, args, kwargs))
                try:
                    cached_result = json.loads(cached_result)
                except:
                    cached_result = {}

                now = time.time()
                age = now - cached_result.get('timestamp', 0) if cached_result else now
                if not cached_result or age > expires:
                    # Have to use try-finally instead of with, since the implementation of __enter__
                    # in redis.lock.Lock automatically blocks https://github.com/andymccurdy/redis-py/blob/master/redis/lock.py
                    # We don't want thread-local storage because we want to release our lock from the
                    # background thread
                    lock = cache_store.lock('__lock_' + fname, timeout=expires, blocking_timeout=0.1, thread_local=False)
                    if lock.acquire():
                        if bg_caching and cached_result and now - cached_result['timestamp'] < stale:
                            # Update redis in the bg, and return the already-cached result, if we already have something
                            # in the cache and it's still valid.
                            try:
                                # update_cache releases the lock when it's done
                                threading.Thread(target=update_cache, args=(f, lock) + args, kwargs=kwargs).start()
                            except Exception as e:
                                lock.release()
                                raise e
                        else:
                            # Otherwise update the cache and return the result of the function in this thread
                            return update_cache(f, lock, *args, **kwargs)
                    else:
                        # Can't get the lock, just return the underlying function
                        if not bg_caching or not cached_result:
                            return f(*args, **kwargs)
                
                return cached_result['result']

            return wrapped
        return decorate
    return cache
