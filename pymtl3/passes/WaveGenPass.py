from __future__ import absolute_import, division, print_function

import time
from collections import defaultdict
from copy import deepcopy

import py
import sys
from pymtl3.dsl import Const
from pymtl3.passes.BasePass import BasePass, PassMetadata

from .errors import PassOrderError



class WaveGenPass( BasePass ):

  def __call__( self, top ):

    if not hasattr( top._sched, "schedule" ):
      raise PassOrderError( "schedule" )

    if hasattr( top, "_cl_trace" ):
      schedule = top._cl_trace.schedule
    else:
      schedule = top._sched.schedule

    top._wav = PassMetadata()

    schedule.append( self.make_wav_gen_func( top, top._wav ) )
  def make_wav_gen_func( self, top, wavmeta ):


        # Preprocess some metadata

    component_signals = defaultdict(set)

    all_components = set()

    # We only collect non-sliced leaf signals
    # TODO only collect leaf signals and for nested structs
    for x in top._dsl.all_signals:
      for y in x.get_leaf_signals():
        host = y.get_host_component()
        component_signals[ host ].add(y)

    # We pre-process all nets in order to remove all sliced wires because
    # they belong to a top level wire and we count that wire

    trimmed_value_nets = []
    wavmeta.clock_net_idx = None

    # FIXME handle the case where the top level signal is in a value net
    for writer, net in top.get_all_value_nets():
      new_net = []
      for x in net:
        if not isinstance(x, Const) and not x.is_sliced_signal():
          new_net.append( x )
          if repr(x) == "s.clk":
            # Hardcode clock net because it needs to go up and down
            assert wavmeta.clock_net_idx is None
            wavmeta.clock_net_idx = len(trimmed_value_nets)

      if new_net:
        trimmed_value_nets.append( new_net )

    # Inner utility function to perform recursive descent of the model.
    # Shunning: I mostly follow v2's implementation

    def recurse_models( m, level ):

      # Special case the top level "s" to "top"

      my_name = m.get_field_name()
      if my_name == "s":
        my_name = "top"

      m_name = repr(m)

      # Define all signals for this model.
      for signal in component_signals[m]:
        trimmed_value_nets.append( [ signal ] )


      # Recursively visit all submodels.
      for child in m.get_child_components():
        recurse_models( child, level+1 )

    # Begin recursive descent from the top-level model.
    recurse_models( top, 0 )



    for i, net in enumerate(trimmed_value_nets):

      # Set this to be the last cycle value
      setattr( wavmeta, "last_{}".format(i), net[0]._dsl.Type().bin() )

    # Now we create per-cycle signal value collect functions

    wavmeta.sim_ncycles = 0

    dump_wav_per_signal = """
      value_str = {1}.bin()
      if "{1}" in wavmeta.sigs:
        sig_val_lst = wavmeta.sigs["{1}"]
        sig_val_lst.append((value_str, wavmeta.sim_ncycles))
        wavmeta.sigs["{1}"] = sig_val_lst
      else:
        wavmeta.sigs["{1}"] = [(value_str, wavmeta.sim_ncycles)]"""

    # TODO type check

    # Concatenate the strings for all signals

    # Give all ' and " characters a preceding backslash for .format
    wav_srcs = []
    for i, net in enumerate( trimmed_value_nets ):
      if i != wavmeta.clock_net_idx:
        wav_srcs.append( dump_wav_per_signal.format( i, net[0]) )

    deepcopy # I have to do this to circumvent the tools

    wavmeta.sigs = {}
    char_length = 5

    src =  """
def dump_wav():
  time.sleep(0.5)
  _tick = u'\u258f'
  _up, _down = u'\u2571', u'\u2572'
  _x, _low, _high = u'\u2573', u'\u005f', u'\u203e'
  _revstart, _revstop = '\x1B[7m', '\x1B[0m'
  _back = '\033[F'
  try:
    # Type check
    {1}
    {2}
  except Exception:
    raise
  if True:
    print("")
    for i in range(wavmeta.sim_ncycles):
        print(" "*(char_length-1) + str(i),end="")
    print("")
    
    size=len(wavmeta.sigs)+1


    for sig in wavmeta.sigs:
      if sig != "s.clk" and sig != "s.reset":

        print("")
        print(sig,end="")
        next_char_length = char_length

        prev_val = None
        for val in wavmeta.sigs[sig]:

          if prev_val is not None:

            if prev_val[0][:3] == '0b0':
              print(_low*char_length,end="")
              if val[1]%5 == 0:
                print(" ",end = "")
              if val[0][:3] == '0b1':
                print(_up,end="")
                next_char_length = char_length - 1
              else:
                next_char_length = char_length
            elif prev_val[0][:3] == '0b1':
              print(_high*char_length,end="")
              if val[1]%5== 0:
                print(" ",end="")
              if val[0][:3] == '0b0':
                print(_down,end = "")
                next_char_length = char_length - 1
              else:
                next_char_length = char_length
          prev_val = val
  wavmeta.sim_ncycles += 1
  print(size*_back)
""".format("", "", "".join(wav_srcs) )

    s, l_dict = top, {}

    exec(compile( src, filename="temp", mode="exec"), globals().update(locals()), l_dict)
    
    return l_dict['dump_wav']
