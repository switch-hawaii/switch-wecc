/*
####################
Add column gen_store_energy_to_power_ratio

Date applied: 2021-06-18
Description:
This script adds a column to the generation_plant
table called gen_storage_energy_to_power_ratio specifying
the storage duration
#################
*/

ALTER TABLE switch.generation_plant ADD COLUMN gen_storage_energy_to_power_ratio real;