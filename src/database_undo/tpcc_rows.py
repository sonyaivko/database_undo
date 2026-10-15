"""
Shared synthetic-row generators for the TPC-C schema. 
tpcc_gen.py, test_correctness.py, sweep_insert.py all use. 
"""
import random
import string
import datetime


def rand_str(n):
    return "".join(random.choices(string.ascii_uppercase + string.ascii_lowercase, k=n))


def rand_zip():
    return "".join(random.choices(string.digits, k=4)) + "11111"


def make_customer_row(c_id, d_id, w_id):
    """Returns a dict keyed by column name. callers build the INSERT's
    column list from dict.keys()"""
    return dict(
        c_id=c_id, c_d_id=d_id, c_w_id=w_id, c_first=rand_str(8), c_middle="OE",
        c_last=rand_str(8), c_street_1=rand_str(16), c_street_2=rand_str(16),
        c_city=rand_str(16), c_state="MA", c_zip=rand_zip(),
        c_phone="".join(random.choices(string.digits, k=10)),
        c_since=datetime.datetime.now(), c_credit=random.choice(["GC", "BC"]),
        c_credit_lim=50000.0, c_discount=round(random.uniform(0.0, 0.5), 4),
        c_balance=-10.0, c_ytd_payment=10.0, c_payment_cnt=1, c_delivery_cnt=0,
        c_data=rand_str(50),
    )