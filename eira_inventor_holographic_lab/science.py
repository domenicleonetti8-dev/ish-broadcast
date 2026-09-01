from __future__ import annotations
import math

G=9.80665

def _num(x): return isinstance(x,(int,float)) and math.isfinite(float(x))
def q(pid,name,value,equation,units="",inputs=None,confidence=1.0):
    return {"part_id":pid,"name":name,"value":float(value),"units":units,"equation":equation,
            "inputs":inputs or {},"source":{"provenance":"calculated","confidence":float(confidence)}}

def preflight(assembly, mesh_metrics=None):
    """Deterministic engineering calculations. Only computes when required inputs exist.
    This is not FEA/CFD; outputs are closed-form/preflight quantities with explicit equations.
    """
    mesh_metrics=mesh_metrics or {}
    out=[]
    for p in assembly.get("parts",[]):
        e=p.get("engineering",{}) or {}; pid=p["part_id"]
        mm=mesh_metrics.get(pid,{})
        volume=e.get("volume_m3", mm.get("volume_m3")); area=e.get("surface_area_m2",mm.get("surface_area_m2"))
        rho=e.get("density_kg_m3")
        if _num(rho) and _num(volume) and rho>0 and volume>0:
            out.append(q(pid,"estimated_mass_kg",rho*volume,"m = rho * V","kg",{"rho":rho,"V":volume}))
        mass=e.get("mass_kg", rho*volume if _num(rho) and _num(volume) else None)
        vel=e.get("velocity_m_s")
        if _num(mass) and _num(vel): out.append(q(pid,"kinetic_energy_J",0.5*mass*vel*vel,"KE = 0.5 m v^2","J",{"m":mass,"v":vel}))
        if _num(mass): out.append(q(pid,"weight_N",mass*G,"W = m g","N",{"m":mass,"g":G}))
        force=e.get("force_N"); loaded_area=e.get("loaded_area_m2",e.get("area_m2"))
        if _num(force) and _num(loaded_area) and loaded_area>0:
            out.append(q(pid,"normal_stress_Pa",force/loaded_area,"sigma = F / A","Pa",{"F":force,"A":loaded_area}))
        young=e.get("youngs_modulus_Pa"); length=e.get("beam_length_m"); I=e.get("second_moment_m4"); load=e.get("point_load_N")
        if all(_num(x) for x in (young,length,I,load)) and young>0 and length>0 and I>0:
            out.append(q(pid,"cantilever_tip_deflection_m",load*length**3/(3*young*I),"delta = F L^3 / (3 E I)","m",{"F":load,"L":length,"E":young,"I":I}))
        k=e.get("effective_length_factor",1.0); axial=e.get("axial_compression_N")
        if all(_num(x) for x in (young,length,I,k)) and young>0 and length>0 and I>0 and k>0:
            pcr=math.pi**2*young*I/(k*length)**2
            out.append(q(pid,"euler_buckling_load_N",pcr,"Pcr = pi^2 E I / (K L)^2","N",{"E":young,"I":I,"K":k,"L":length}))
            if _num(axial) and axial>0: out.append(q(pid,"buckling_safety_factor",pcr/axial,"SF = Pcr / P","ratio",{"Pcr":pcr,"P":axial}))
        voltage=e.get("voltage_V"); current=e.get("current_A"); resistance=e.get("resistance_ohm")
        if _num(voltage) and _num(current): out.append(q(pid,"electrical_power_W",voltage*current,"P = V I","W",{"V":voltage,"I":current}))
        if _num(current) and _num(resistance): out.append(q(pid,"joule_heating_W",current*current*resistance,"P = I^2 R","W",{"I":current,"R":resistance}))
        flow=e.get("volumetric_flow_m3_s"); farea=e.get("flow_area_m2")
        if _num(flow) and _num(farea) and farea>0:
            v=flow/farea; out.append(q(pid,"mean_flow_velocity_m_s",v,"v = Q / A","m/s",{"Q":flow,"A":farea}))
            frho=e.get("fluid_density_kg_m3"); mu=e.get("dynamic_viscosity_Pa_s"); dh=e.get("hydraulic_diameter_m")
            if all(_num(x) for x in (frho,mu,dh)) and mu>0 and dh>0:
                Re=frho*v*dh/mu; out.append(q(pid,"reynolds_number",Re,"Re = rho v Dh / mu","ratio",{"rho":frho,"v":v,"Dh":dh,"mu":mu}))
                rough=e.get("roughness_m",0.0); L=e.get("pipe_length_m")
                if _num(L) and L>0 and Re>0:
                    if Re<2300: ff=64/Re
                    else:
                        rr=max(0.0,float(rough))/dh
                        ff=0.25/(math.log10(rr/3.7+5.74/Re**0.9)**2)
                    dp=ff*(L/dh)*(frho*v*v/2)
                    out.append(q(pid,"darcy_pressure_drop_Pa",dp,"dP = f (L/Dh) rho v^2 / 2","Pa",{"f":ff,"L":L,"Dh":dh,"rho":frho,"v":v}))
        kcond=e.get("thermal_conductivity_W_mK"); thickness=e.get("thickness_m"); dT=e.get("delta_T_K"); heat_area=e.get("heat_transfer_area_m2",loaded_area)
        if all(_num(x) for x in (kcond,thickness,dT,heat_area)) and thickness>0 and heat_area>0:
            out.append(q(pid,"conductive_heat_rate_W",kcond*heat_area*dT/thickness,"Qdot = k A dT / L","W",{"k":kcond,"A":heat_area,"dT":dT,"L":thickness}))
        omega=e.get("angular_speed_rad_s"); inertia=e.get("rotational_inertia_kg_m2")
        if _num(omega) and _num(inertia): out.append(q(pid,"rotational_energy_J",0.5*inertia*omega*omega,"Erot = 0.5 I omega^2","J",{"I":inertia,"omega":omega}))
        if _num(area): out.append(q(pid,"surface_area_m2",area,"mesh surface integration","m^2",{},0.99))
        if _num(volume) and volume>0: out.append(q(pid,"volume_m3",volume,"closed mesh volume integration","m^3",{},0.99))
    return out
