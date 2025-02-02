# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe local transmission & distribution
build-outs for the Switch model. This adds a virtual "distribution node"
to each load zone that is connected to the zone's central node via a
distribution pathway that incurs distribution losses. Distributed Energy
Resources (DER) impact the energy balance at the distribution node, avoiding
losses from the distribution network.

INPUT FILE FORMAT
    Import local transmission & distribution data. The following files
    are expected in the input directory. Both files will
    contain additional columns that are used by the load_zones module
    and transmission.transport.build module.

    load_zones.csv
        load_zone, existing_local_td, local_td_annual_cost_per_mw

    trans_params.csv
        distribution_loss_rate

    If distribution_loss_rate is not specified, or if trans_params.csv doesn't
    exist, mod.distribution_loss_rate will default to 0.053.
"""
from __future__ import division

import os
from pyomo.environ import *

dependencies = 'switch_model.timescales', 'switch_model.balancing.load_zones',\
    'switch_model.financials'

def define_dynamic_lists(mod):
    """
    Distributed_Power_Injections and Distributed_Power_Withdrawals are lists
    of Distributed Energy Resource (DER) model components that inject and
    withdraw from a load zone's distributed node. Distributed_Power_Injections
    is initially set to InjectIntoDistributedGrid, and
    Distributed_Power_Withdrawals is initial set to zone_demand_mw. Each
    component in either of these lists will need to be indexed by (z,t) across
    all LOAD_ZONES and TIMEPOINTS, and needs to be in units of MW.
    """
    mod.Distributed_Power_Injections = []
    mod.Distributed_Power_Withdrawals = []


def define_components(mod):
    """

    Define local transmission and distribution portions of an electric grid.
    This models load zones as two nodes: the central grid node described in
    the load_zones module, and a distributed (virtual) node that is connected
    to the central bus via a local_td pathway with losses described by
    distribution_loss_rate. Distributed Energy Resources (DER) such as
    distributed solar, demand response, efficiency programs, etc will need to
    register with the Distributed_Power_Withdrawals and Distributed_Power_Injections lists
    which are used for power balance equations. This module is divided into
    two sections: the distribution node and the local_td pathway that connects
    it to the central grid.

    Note: This module interprets the parameter zone_demand_mw[z,t] as the end-
    use sales rather than the withdrawals from the central grid, and moves
    zone_demand_mw from the Zone_Power_Withdrawals list to the
    Distributed_Power_Withdrawals list so that distribution losses can be accounted
    for.

    Unless otherwise stated, all power capacity is specified in units of MW and
    all sets and parameters are mandatory.

    DISTRIBUTED NODE

    WithdrawFromCentralGrid[z, t] is a decision variable that describes the
    power exchanges between the central grid and the distributed network, from
    the perspective of the central grid. We currently prohibit injections into
    the central grid because it would create a mathematical loophole for
    "spilling power" and we currently lack use cases that need this. We cannot
    use a single unsigned variable for this without introducing errrors in
    calculating Local T&D line losses. WithdrawFromCentralGrid is added to the
    load_zone power balance, and has a corresponding expression from the
    perspective of the distributed node:

    InjectIntoDistributedGrid[z,t] = WithdrawFromCentralGrid[z,t] * (1-distribution_loss_rate)

    The Distributed_Energy_Balance constraint is defined in define_dynamic_components.

    LOCAL_TD PATHWAY

    existing_local_td[z in LOAD_ZONES] is the amount of local transmission and
    distribution capacity in MW that is in place prior to the start of the
    study. This is assumed to remain in service throughout the study.

    BuildLocalTD[load_zone, period] is a decision variable
    describing how much local transmission and distribution to add in each load
    zone during each study period.

    LocalTDCapacity[z, period] is an expression that describes how much local
    transmission and distribution has been built to date in each load zone.
    Without demand response or distributed generation, the optimal value of this
    expression is simply the load zone's peak expected load. With demand
    response or distributed generation, this decision becomes less obvious. Then
    Switch will consider scheduling load to absorb peak utility-scale solar,
    increasing local T&D requirements, or adding more distributed solar,
    potentially decreasing local T&D requirements.

    distribution_loss_rate is the ratio of average losses for local T&D. This
    value is relative to delivered energy, so the total energy needed is load
    * (1 + distribution_loss_rate). This optional value defaults to 0.053
    based on ReEDS Solar Vision documentation:
    http://www1.eere.energy.gov/solar/pdfs/svs_appendix_a_model_descriptions_data.pdf

    Meet_Local_TD[z, period] is a constraint that enforces minimal
    local T&D requirements.
        LocalTDCapacity >= max_local_demand

    local_td_annual_cost_per_mw[z in LOAD_ZONES] describes the total
    annual costs for each MW of local transmission & distribution. This
    value should include the annualized capital costs as well as fixed
    operations & maintenance costs. These costs will be applied to
    existing and new infrastructure. We assume that existing capacity
    will be replaced at the end of its life, so these costs will
    continue indefinitely.

    --- NOTES ---

    Switch 2 treats all transmission and distribution (long- distance or local)
    the same. Any capacity that is built will be kept online indefinitely. At
    the end of its financial lifetime, existing capacity will be retired and
    rebuilt, so the annual cost of a line upgrade will remain constant in every
    future year. See notes in the trans_build module for a more detailed
    comparison to Switch 1.

    """

    # Local T&D
    mod.existing_local_td = Param(mod.LOAD_ZONES, within=NonNegativeReals, input_file="load_zones.csv")
    mod.min_data_check('existing_local_td')

    mod.BuildLocalTD = Var(
        mod.LOAD_ZONES, mod.PERIODS,
        within=NonNegativeReals)
    mod.LocalTDCapacity = Expression(
        mod.LOAD_ZONES, mod.PERIODS,
        rule=lambda m, z, period:
            m.existing_local_td[z]
            + sum(
                m.BuildLocalTD[z, bld_yr]
                for bld_yr in m.CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[period]
        )
    )
    mod.distribution_loss_rate = Param(default=0.053, input_file="trans_params.csv")

    mod.Meet_Local_TD = Constraint(
        mod.EXTERNAL_COINCIDENT_PEAK_DEMAND_ZONE_PERIODS,
        rule=lambda m, z, period:
            m.LocalTDCapacity[z, period] * (1-m.distribution_loss_rate)
            >=
            m.zone_expected_coincident_peak_demand[z, period]
    )
    mod.local_td_annual_cost_per_mw = Param(
        mod.LOAD_ZONES,
        within=NonNegativeReals, input_file="load_zones.csv")
    mod.min_data_check('local_td_annual_cost_per_mw')
    mod.LocalTDFixedCosts = Expression(
        mod.PERIODS,
        doc="Summarize annual local T&D costs for the objective function.",
        rule=lambda m, p: sum(
            m.LocalTDCapacity[z, p] * m.local_td_annual_cost_per_mw[z]
            for z in m.LOAD_ZONES))
    mod.Cost_Components_Per_Period.append('LocalTDFixedCosts')


    # DISTRIBUTED NODE
    mod.WithdrawFromCentralGrid = Var(
        mod.ZONE_TIMEPOINTS,
        within=NonNegativeReals,
        doc="Power withdrawn from a zone's central node sent over local T&D.")
    mod.Enforce_Local_TD_Capacity_Limit = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t:
            m.WithdrawFromCentralGrid[z,t] <= m.LocalTDCapacity[z,m.tp_period[t]])
    mod.InjectIntoDistributedGrid = Expression(
        mod.ZONE_TIMEPOINTS,
        doc="Describes WithdrawFromCentralGrid after line losses.",
        rule=lambda m, z, t: m.WithdrawFromCentralGrid[z,t] * (1-m.distribution_loss_rate))

    # Register energy injections & withdrawals
    mod.Zone_Power_Withdrawals.append('WithdrawFromCentralGrid')
    mod.Distributed_Power_Injections.append('InjectIntoDistributedGrid')


def define_dynamic_components(mod):
    """

    Adds components to a Pyomo abstract model object to enforce the
    first law of thermodynamics at the level of distibuted nodes. Unless
    otherwise stated, all terms describing power are in units of MW and
    all terms describing energy are in units of MWh.

    Distributed_Energy_Balance[z, t] is a constraint that sets the sums of
    Distributed_Power_Injections and Distributed_Power_Withdrawals equal to
    each other in every zone and timepoint. The term tp_duration_hrs is
    factored out of the equation for brevity.

    """

    mod.Distributed_Energy_Balance = Constraint(
        mod.ZONE_TIMEPOINTS,
        rule=lambda m, z, t: (
            sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Power_Injections
            ) == sum(
                getattr(m, component)[z, t]
                for component in m.Distributed_Power_Withdrawals)))