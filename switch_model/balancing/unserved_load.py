# Copyright (c) 2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines components to allow leaving some load unserved. This module is
specially useful when running production costing simulations, though not
strictly required in all cases.

INPUT FILE FORMAT
    The cost penalty of unserved load in units of $/MWh is the only parameter
    that can be inputted. The following file is not mandatory, because the
    parameter defaults to a value of 500 $/MWh. This file contains one header
    row and one data row.

    optional input files:
        lost_load_cost.csv
            unserved_load_penalty
"""

import os
from pyomo.environ import *

dependencies = 'switch_model.timescales',\
    'switch_model.balancing.load_areas', 'switch_model.financials'

def define_components(mod):
    """

    Augments the model with the capability of leaving some load unserved
    at a cost.

    unserved_load_penalty[z] is the cost penalty of not supplying 1 MWh of
    load in any load zone.

    UnservedLoad[z, tp] is a decision variable that describes how much
    load in MWh is not supplied in a given load zone, at a given timepoint.

    UnservedLoadPenalty[tp] is an expression that summarizes the cost penalties
    of the load that is left unserved in all load zones at a given timepoint.

    """

    mod.unserved_load_penalty = Param(
        within=NonNegativeReals,
        input_file="lost_load_cost.csv",
        default=500)
    mod.UnservedLoad = Var(
        mod.LOAD_ZONES, mod.TIMEPOINTS,
        within=NonNegativeReals)
    mod.Zone_Power_Injections.append('UnservedLoad')

    mod.UnservedLoadPenalty = Expression(
        mod.TIMEPOINTS,
        rule=lambda m, tp: sum(m.UnservedLoad[z, tp] *
            m.unserved_load_penalty for z in m.LOAD_ZONES))
    mod.Cost_Components_Per_TP.append('UnservedLoadPenalty')