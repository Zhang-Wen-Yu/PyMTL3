"""
========================================================================
SendRecvIfc.py
========================================================================
RTL implementation of en/rdy micro-protocol.

Author: Yanghui Ou, Shunning Jiang
  Date: May 5, 2019
"""
from __future__ import absolute_import, division, print_function

from pymtl import *

from .ifcs_utils import enrdy_to_str
from .GuardedIfc import *

#-------------------------------------------------------------------------
# RecvIfcRTL
#-------------------------------------------------------------------------

class RecvIfcRTL( Interface ):

  def construct( s, Type ):

    s.msg =  InPort( Type )
    s.en  =  InPort( int if Type is int else Bits1 )
    s.rdy = OutPort( int if Type is int else Bits1 )

    s.MsgType = Type

  def line_trace( s ):
    return enrdy_to_str( s.msg, s.en, s.rdy )

  def __str__( s ):
    return s.line_trace()

  def connect( s, other, parent ):

    # We are doing SendCL (other) -> [ RecvCL -> SendRTL ] -> RecvRTL (s)
    # SendCL is a caller interface
    if isinstance( other, GuardedCallerIfc ):
      m = RecvCL2SendRTL( s.MsgType )

      if hasattr( parent, "RecvCL2SendRTL_count" ):
        count = parent.RecvCL2SendRTL_count
        setattr( parent, "RecvCL2SendRTL_" + str( count ), m )
        parent.connect_pairs(
          other,  m.recv,
          m.send.msg, s.msg,
          m.send.en,  s.en,
          m.send.rdy, s.rdy
        )
        parent.RecvCL2SendRTL_count += 1
        return True

      else:
        parent.RecvCL2SendRTL_0 = m
        parent.connect_pairs(
          other, m.recv,
          m.send.msg, s.msg,
          m.send.en,  s.en,
          m.send.rdy, s.rdy,
        )
        parent.RecvCL2SendRTL_count = 1
        return True
    return False

#-------------------------------------------------------------------------
# SendIfcRTL
#-------------------------------------------------------------------------

class SendIfcRTL( Interface ):

  def construct( s, Type ):
    s.msg = OutPort( Type )
    s.en  = OutPort( int if Type is int else Bits1 )
    s.rdy =  InPort( int if Type is int else Bits1 )

    s.MsgType = Type

  def line_trace( s ):
    return enrdy_to_str( s.msg, s.en, s.rdy )

  def __str__( s ):
    return s.line_trace()

  def connect( s, other, parent ):

    # We are doing SendRTL (s) -> [ RecvRTL -> SendCL ] -> RecvCL (other)
    # RecvCL is a callee interface
    if isinstance( other, GuardedCalleeIfc ):
      m = RecvRTL2SendCL( s.MsgType )

      if hasattr( parent, "RecvRTL2SendCL_count" ):
        count = parent.RecvRTL2SendCL_count
        setattr( parent, "RecvRTL2SendCL_" + str( count ), m )
        parent.connect_pairs(
          m.send, other,
          s.msg, m.recv.msg,
          s.en,  m.recv.en,
          s.rdy, m.recv.rdy,
        )
        parent.RecvRTL2SendCL_count += 1
        return True

      else:
        parent.RecvRTL2SendCL_0 = m
        parent.connect_pairs(
          m.send, other,
          s.msg, m.recv.msg,
          s.en,  m.recv.en,
          s.rdy, m.recv.rdy,
        )
        parent.RecvRTL2SendCL_count = 1
        return True
    return False
"""
========================================================================
Send/RecvIfc adapters
========================================================================
CL/RTL adapters for send/recv interface.

Author : Yanghui Ou
  Date : Mar 07, 2019
"""

#-------------------------------------------------------------------------
# RecvCL2SendRTL
#-------------------------------------------------------------------------

class RecvCL2SendRTL( Component ):

  def construct( s, MsgType ):

    # Interface

    s.send = SendIfcRTL( MsgType )

    s.recv_called = False
    s.recv_rdy    = False
    s.msg_to_send = 0

    @s.update
    def up_send_rtl():
      s.send.en     = Bits1( 1 ) if s.recv_called else Bits1( 0 )
      s.send.msg    = s.msg_to_send
      s.recv_called = False

    @s.update
    def up_recv_rdy_cl():
      s.recv_rdy    = True if s.send.rdy else False

    s.add_constraints(
      U( up_recv_rdy_cl ) < M( s.recv ),
      U( up_recv_rdy_cl ) < M( s.recv.rdy ),
      M( s.recv.rdy ) < U( up_send_rtl ),
      M( s.recv ) < U( up_send_rtl )
    )

  @guarded_ifc( lambda s : s.recv_rdy )
  def recv( s, msg ):
    s.msg_to_send = msg
    s.recv_called = True

  def line_trace( s ):
    return "{}(){}".format(
      enrdy_to_str( s.msg_to_send, s.recv_called, s.recv_rdy ),
      s.send.line_trace()
    )
#-------------------------------------------------------------------------
# RecvRTL2SendCL
#-------------------------------------------------------------------------

class RecvRTL2SendCL( Component ):

  def construct( s, MsgType ):

    # Interface

    s.recv = RecvIfcRTL( MsgType )
    s.send = GuardedCallerIfc()

    s.sent_msg = None
    s.send_rdy = False

    @s.update
    def up_recv_rtl_rdy():
      s.send_rdy = s.send.rdy() and not s.reset
      s.recv.rdy = Bits1( 1 ) if s.send.rdy() and not s.reset else Bits1( 0 )

    @s.update
    def up_send_cl():
      s.sent_msg = None
      if s.recv.en:
        s.send( s.recv.msg )
        s.sent_msg = s.recv.msg

    s.add_constraints( U( up_recv_rtl_rdy ) < U( up_send_cl ) )

  def line_trace( s ):
    return "{}(){}".format(
      s.recv.line_trace(),
      enrdy_to_str( s.sent_msg, s.sent_msg is not None, s.send_rdy )
    )
