from __future__ import print_function
import time
from redis import Redis
from itertools import count
import sys
from dispatch import Dispatch, iter_pmt_hits, get_trigger_type

redis = Redis()

# triggers, note: the order here is important!
# the position of the trigger in the list corresponds to the bit in the
# trigger word.
# http://snopl.us/docs/rat/user_manual/html/node43.html
TRIGGER_NAMES = \
['100L',
 '100M',
 '100H',
 '20',
 '20LB',
 'ESUML',
 'ESUMH',
 'OWLN',
 'OWLEL',
 'OWLEH',
 'PULGT',
 'PRESCL',
 'PED',
 'PONG',
 'SYNC',
 'EXTA',
 'EXT2',
 'EXT3',
 'EXT4',
 'EXT5',
 'EXT6',
 'EXT7',
 'EXT8',
 'SRAW',
 'NCD',
 'SOFGT',
 'MISS']

def dispatch_worker(host):
    """Connects to a dispatcher at ip address `host` and processes the dispatch stream."""
    import ratzdab

    dispatcher = Dispatch(host)

    for i in count():
        try:
            pev = dispatcher.next(False)
        except (NotImplementedError, ValueError):
            pass
        except Exception as e:
            print(e,file=sys.stderr)
            continue

        # unix timestamp
        now = int(time.time())

        if i % 10 == 0:
            # heartbeat information
            p = redis.pipeline()
            p.set('dispatcher',host)
            p.expire('dispatcher',60)

            # int:{interval}:id:{timestamp}:name:{name}
            key = 'stream/int:{0:d}:id:{1:d}:name:{2:s}'
            for t in [1,60,3600]:
                id = now//t
                # expire in 100,000*[time interval]
                expire = t*100000
                p.set(key.format(t,id,'heartbeat'),1)
                p.expire(key.format(t,id,'heartbeat'),expire)

            p.execute()

        if not o:
            time.sleep(0.01)
            continue

        gtid = pev.MTCReadoutData.BcGT
        nhit = pev.NPmtHit
        run = pev.RunNumber
        subrun = pev.DAQCodeVersion # seriously :)
        trig = get_trigger_type(pev)

        event_key = '{0:d}:{1:d}'.format(run,gtid)
        if not redis.zadd('gtids',event_key,-now):
            # event is already processed
            continue

        # trim gtid list to 100 elements
        redis.zremrangebyrank('gtids',100,-1)

        # for docs on redis pipeline see http://redis.io/topics/pipelining
        p = redis.pipeline(transaction=False)

        qhs_sum = 0.0
        for pmt in iter_pmt_hits(pev):
            id = 16*32*pmt.CrateID + 32*pmt.BoardID + pmt.ChannelID
            p.incr('events/id:{0:d}:count'.format(now//60))
            p.expire('events/id:{0:d}:count'.format(now//60),600)
            key = 'events/id:{0:d}:channel:{1:d}'
            p.incr(key.format(now//60,id))
            p.expire(key.format(now//60,id),600)

            qhs_sum += pmt.Qhs

        # nhit distribution
        # see http://flask.pocoo.org/snippets/71/ for this design pattern
        p.lpush('events/id:{0:d}:name:nhit'.format(now),nhit)
        p.expire('events/id:{0:d}:name:nhit'.format(now),3600)

        # int:{interval}:id:{timestamp}:name:{name}
        key = 'stream/int:{0:d}:id:{1:d}:name:{2:s}'
        for t in [1,60,3600]:
            id = now//t
            # expire in 100,000*[time interval]
            expire = t*100000
            # total trigger count
            p.incr(key.format(t,id,'TOTAL'))
            p.expire(key.format(t,id,'TOTAL'),expire)
            # nhit
            p.incrby(key.format(t,id,'TOTAL:nhit'),nhit)
            p.expire(key.format(t,id,'TOTAL:nhit'),expire)
            # charge
            p.incrbyfloat(key.format(t,id,'TOTAL:charge'),qhs_sum)
            p.expire(key.format(t,id,'TOTAL:charge'),expire)
            # run
            p.set(key.format(t,id,'run'),run)
            p.expire(key.format(t,id,'run'),expire)
            # subrun
            p.set(key.format(t,id,'subrun'),subrun)
            p.expire(key.format(t,id,'subrun'),expire)
            # gtid
            p.set(key.format(t,id,'gtid'),gtid)
            p.expire(key.format(t,id,'gtid'),expire)

        for i, name in enumerate(TRIGGER_NAMES):
            if trig & (1 << i):
                for t in [1,60,3600]:
                    id = now//t
                    expire = t*100000
                    # trigger rate
                    p.incr(key.format(t,id,name))
                    p.expire(key.format(t,id,name),expire)
                    # nhit
                    p.incrby(key.format(t,id,name + ':nhit'),nhit)
                    p.expire(key.format(t,id,name + ':nhit'),expire)
                    # charge
                    p.incrbyfloat(key.format(t,id,name + ':charge'),qhs_sum)
                    p.expire(key.format(t,id,name + ':charge'),expire)

        p.execute()
