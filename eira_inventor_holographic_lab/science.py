from __future__ import annotations
import math

def preflight(assembly):
    out=[]
    for p in assembly.get("parts",[]):
        e=p.get("engineering",{}); mid=p["part_id"]
        mass=e.get("mass_kg"); vel=e.get("velocity_m_s")
        if _num(mass) and _num(vel): out.append(q(mid,"kinetic_energy_J",0.5*mass*vel*vel,"0.5*m*v^2"))
        force=e.get("force_N"); area=e.get("area_m2")
        if _num(force) and _num(area) and area>0: out.append(q(mid,"normal_stress_Pa",force/area,"F/A"))
        voltage=e.get("voltage_V"); current=e.get("current_A")
        if _num(voltage) and _num(current): out.append(q(mid,"electrical_power_W",voltage*current,"V*I"))
        flow=e.get("volumetric_flow_m3_s"); farea=e.get("flow_area_m2")
        if _num(flow) and _num(farea) and farea>0: out.append(q(mid,"mean_flow_velocity_m_s",flow/farea,"Q/A"))
        rho=e.get("density_kg_m3"); vol=e.get("volume_m3")
        if _num(rho) and _num(vol) and rho>0 and vol>0: out.append(q(mid,"estimated_mass_kg",rho*vol,"rho*V"))
    return out

def _num(x): return isinstance(x,(int,float)) and math.isfinite(float(x))
def q(pid,name,value,equation): return {"part_id":pid,"name":name,"value":value,"equation":equation,"source":{"provenance":"calculated","confidence":1.0}}
