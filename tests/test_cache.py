from __future__ import print_function

import time
import threading
import uuid
import unittest

from multiprocessing.pool import ThreadPool

from steadycache import cache

class MockCache(dict):
    """ Class implementing required cache store object methods"""
    def __init__(self, *args, **kwargs):
        self.locks = {}
        super(MockCache, self).__init__(self, *args, **kwargs)

    def set(self, key, value):
        t = self.setdefault('__count_' + key, 0)
        self['__count_' + key] = t + 1
        self[key] = value
        print(key + ": " + value)

    def get_count(self, key):
        """ Helper method to see how many times a cache was set """
        return self['__count_' + key]

    def lock(self, name, timeout=None, sleep=0.1, blocking_timeout=None, thread_local='whatever'):
        this = self

        class MockLock():
            """ Lock class mimicking redis's Lock functionality for testing """
            def __init__(self, name):
                self.name = name
                self.uuid = str(uuid.uuid4())
                self.lock = threading.Lock()

            def release(self):
                if '__lock_' + self.name in this and this['__lock_' + self.name]['uuid'] == self.uuid:
                    del this['__lock_' + self.name]
                    self.lock.release()
                    print("Released " + self.name)
                else:
                    raise Exception("WE SHOULD NOT BE HERE! Race condition! Did not release self")

            def acquire(self):
                slept = 0
                print("Acquiring " + self.name + " " + str(self.lock))
                print(this.__repr__)
                while not self.lock.acquire(False):
                    age = time.time() - this['__lock_' + self.name]['timestamp']
                    print(age)
                    if age < (this['__lock_' + self.name]['timeout'] or float('inf')):
                        if blocking_timeout and slept > blocking_timeout:
                            "Failed to acquire " + self.name
                            return False

                        "Sleeping for {} seconds waiting for {}".format(sleep, self.name)
                        time.sleep(sleep)
                        slept += sleep

                    else:
                        print("Lock " + self.name + " timed out.")
                        self.release()

                # XXX: This should be atomic enough for tests in cpython considering the GIL?
                this['__lock_' + self.name] = {'timestamp': time.time(), 'timeout': timeout, 'uuid': self.uuid}
                print("Acquired " + self.name)
                return True
        return self.locks.setdefault(name, MockLock(name))


class TestCache(unittest.TestCase):
    def setUp(self):
        self.mock_redis = MockCache()
        self.cache = cache.create_cache(self.mock_redis)

    def test_cache_caches(self):
        self.count_foo = 0

        @self.cache(prefix="test_cache_caches")
        def foo():
            self.count_foo += 1
            return self.count_foo

        self.assertEqual(foo(), 1)
        self.assertEqual(foo(), 1)

    def test_cache_expires(self, expires=5):
        self.count_foo = 0

        @self.cache(prefix="test_cache_expires")
        def foo():
            self.count_foo += 1
            return self.count_foo

        self.count_bar = 0

        @self.cache(expires=0.5)
        def bar():
            self.count_bar += 1
            return self.count_bar

        self.assertEqual(foo(), 1)
        time.sleep(4.9)
        self.assertEqual(foo(), 1)
        # Sleep longer than the cache expiry time
        time.sleep(0.11)
        self.assertEqual(foo(), 2)

        # Test explicit expiry time < 1 sec
        self.assertEqual(bar(), 1)
        time.sleep(0.1)
        self.assertEqual(bar(), 1)
        # Sleep longer than the cache expiry time
        time.sleep(0.41)
        self.assertEqual(bar(), 2)

    def test_prefixes(self):
        """
        Make sure that two functions with the same name cache the right values when given a unique prefix
        """
        this = self

        class A():
            @staticmethod
            @this.cache(prefix="test_prefixes_A")
            def foo():
                return 'A'

        class B():
            @staticmethod
            @this.cache(prefix="test_prefixes_B")
            def foo():
                return 'B'

        self.assertNotEqual(A.foo(), B.foo())

    def test_name_clash_exception(self):
        """
        Creating a cache for two functions that have the same name without specifying a prefix for at least one
        of them should cause an exception.

        I don't know how to make this happen yet, so this test is currently failing
        """
        try:
            class A():
                @self.cache()
                def foo():
                    return 'A'

            class B():
                @self.cache()
                def foo():
                    return 'B'
        except cache.CacheNameClashException:
            pass

        else:
            self.fail()

    def test_update_lock(self):
        """
        Test that locking for updating the cache works
        """
        @self.cache(expires=0.5, prefix='test_update_lock')
        def foo():
            # Sleep longer than expiry
            time.sleep(1)
            return time.time()

        t1 = foo()
        time.sleep(0.6)

        pool = ThreadPool(processes=1)
        async_result = pool.apply_async(foo, ())

        time.sleep(0.1)
        t3 = foo()
        t2 = async_result.get()

        # The time we get should be immediate from cache and the same as t2
        self.assertEqual(foo(), t2)

        # Make sure that the expires worked
        self.assertNotEqual(t1, t3)

        # This was run without a sliding cache, so t2 and t3 should not be the same
        self.assertNotEqual(t3, t2)

    def test_bg_caching(self):
        """
        Test that cache is invalidated and updated, but stale results are returned when background caching is enabled
        """
        self.count_foo = 0

        def foo_():
            time.sleep(1)
            return time.time()

        foo = self.cache(bg_caching=True, prefix="test_bg_caching", expires=1)(foo_)

        t1 = foo()
        # Invalidate the cache
        time.sleep(1.1)

        pool = ThreadPool(processes=3)
        t2_ = pool.apply_async(foo, ())
        t3_ = pool.apply_async(foo, ())
        t4_ = pool.apply_async(foo, ())

        t2 = t2_.get()
        t3 = t3_.get()
        t4 = t4_.get()

        # Cache should return stale results until new ones are valid
        print(self.mock_redis)
        self.assertEqual(t2, t1)
        self.assertEqual(t3, t1)
        self.assertEqual(t4, t1)

        time.sleep(1.1)

        # The cache should only have been updated once, by t2
        # XXX: Test fname
        fname = "test_bg_caching" + "_" + foo.__module__ + "_" + foo.__name__

        # mangle() has to have access to the undecorated function
        self.assertEqual(self.mock_redis.get_count(cache.mangle(fname, foo_, (), {})), 2)

    def test_arguments_caching(self):
        # Test that functions calls with differing argument resolve to
        # different cache keys
        @self.cache(prefix="test_arguments_caching")
        def foo(bar):
            return bar + " " + str(time.time())

        @self.cache(prefix="test_arguments_caching")
        def baz(bar='a'):
            return bar + " " + str(time.time())

        a = foo('a')
        b = foo('b')
        c = foo('b')

        self.assertNotEqual(a, b)
        self.assertEqual(b, c)

        a = baz()
        b = baz('a')  # This is logically equivalent to a
        c = baz('b')
        d = baz(bar='b')

        self.assertEqual(a, b)
        self.assertNotEqual(b, c)
        self.assertEqual(c, d)


    def test_kwargs_caching(self):
        @self.cache(prefix="test_kwargs_caching")
        def bax(a, b):
            return str(a) + " " + str(time.time())

        @self.cache(prefix="test_kwargs_caching")
        def baw(a=1, b=1):
            return str(a) + " " + str(b) + " " + str(time.time())

        # Test that ordering does not matter for argument values
        a = bax(1, 2)
        b = bax(2, 1)
        self.assertNotEqual(a, b)

        # Test that keyword arguments are handled correctly
        # 1. Implicit and explicit keyword arguments are equivalent
        # 2. Order does not matter
        a = baw()
        b = baw(2)

        c = baw(1, 2)
        d = baw(2, 1)

        e = baw(1, b=2)
        f = baw(2, b=1)

        g = baw(a=1, b=2)
        h = baw(a=2, b=1)

        i = baw(b=2, a=1)
        j = baw(b=1, a=2)

        self.assertNotEqual(a, b)

        self.assertEqual(b, d)
        self.assertEqual(c, e)
        self.assertEqual(e, g)
        self.assertEqual(g, i)

        self.assertEqual(d, f)
        self.assertEqual(f, h)
        self.assertEqual(h, j)

        # Take advantage of transitivity of equality to see that all above
        # pairs are not the same and are not the same as `a`
        self.assertNotEquals(a, c)
        self.assertNotEquals(a, d)
        self.assertNotEqual(c, d)


    def test_stale(self):
        # Test that a stale cache is invalidated
        @self.cache(prefix="test_stale", expires=0.1, bg_caching=True, stale=0.2)
        def foo():
            time.sleep(0.2)
            return time.time()

        a = foo()
        time.sleep(0.2)
        now = time.time()
        b = foo()
        now2 = time.time()
        self.assertNotEqual(a, b)
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertGreater(now2 - now, 0.2)

    def tearDown(self):
        pass


if __name__ == "__main__":
    unittest.main()
