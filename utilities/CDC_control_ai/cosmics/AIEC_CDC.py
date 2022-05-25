#!/gluonfs1/gapps/python/VENV/hoss_hydra_20201112/venv/bin/python3 -W ignore
import os
import subprocess
import time
import argparse
import MySQLdb
import logging
import json
import sys
import ast
import datetime

import subprocess
from subprocess import call
from subprocess import Popen, PIPE
from multiprocessing import Process, Queue

from matplotlib.font_manager import json_dump
import cdc_loadmodel as loadmodel
import cdc_runai as runai

EPICS=True
try:
    from epics import caget,caput
except:
    print("Cannot load EPICS libraries. Disabling EPICS...")
    EPICS=False

ops_dbcnx=MySQLdb.connect(host="epscidb", user="aiecuser", db="AIEC_ops")
ops_dbcursor=ops_dbcnx.cursor(MySQLdb.cursors.DictCursor)


def ProcessRecommend(config_file):
    # reads the latest recommendation from the database and uses the cdc_tool to set HV to the recommended value
    #TODO: What about when human intervention is required?
    
    while(True):
        with open(config_file) as config_json:
                configuration=json.load(config_json)

        poll_time=configuration['poll_time'] #minutes
        control_window=configuration['control_window'] #[2210.0V,2250.0V]
        require_human=configuration['require_human']
        control_mask=configuration['control_mask']

        pollq_s="SELECT * from GlueX_CDC where Recommend=1 && Accepted is NULL ORDER BY ID desc limit 1;"
        ops_dbcursor.execute(pollq_s)
        latest_rec=ops_dbcursor.fetchall()
        print("latest recommendation:",latest_rec)
        if len(latest_rec) != 0:
            hvset=ast.literal_eval(latest_rec[0]["OutputDict"].decode('utf-8'))["hv_set"]
            recommended_V=int(float(hvset)+0.5)
            print("Recommended HV is ",recommended_V)

            if len(control_window) != 0:
                if(recommended_V>control_window[1]):
                    recommended_V=control_window[1]
            
                if(recommended_V<control_window[0]):
                    recommended_V=control_window[0]

            if(require_human==1):
                print("Human intervention required")
                #get human intervention
            else:
                print("No human intervention required")
                #use AI

                hvset_req="/group/halld/AIEC/utilities/cdc_tool.py --hvset "+control_mask+" "+str(recommended_V)
                print(hvset_req)
                update_q="UPDATE GlueX_CDC SET Accepted=NOW() WHERE ID=%s" % (latest_rec[0]['ID'])
                print(update_q)
                
                if(configuration["debug"]==0):
                    
                    hvset = Popen(hvset_req,stdin=PIPE,stdout=PIPE, stderr=PIPE,bufsize=-1,shell=True)
                    hvset_out, errors = hvset.communicate()
                    print(hvset_out)
                    ops_dbcursor.execute(update_q)
                    ops_dbcnx.commit()
                else:
                    print("DEBUG: skipping HV set")
                    print("DEBUG: skipping update")
        
        time.sleep(1.02*60*poll_time)

def ProcessEPICS(epics_out,def_hvbi=0,isInit=False,def_temp=0,def_pressure=0,ideal_gcf=0.141):
# takes in a block of text from EPICS, respects fixed (negative) hvbi,temp,pressure, passes through ideal_gcf and either 
# returns a suitable dictionary for the AI model

    #print("EPICS data: ",epics_out)
    
    tempsum = 0.0
    badepics = 0

    for line in str(epics_out,'utf-8').splitlines():
        #print(line)
        if 'N/A' in line and 'IBCAD00CRCUR6' not in line:
            badepics = 1
            break
    
        elif 'N/A' in line and 'IBCAD00CRCUR6' in line:
            continue

        ename = line.split()[0]
        emean = line.split()[2]
        emax = line.split()[3]
        esd = line.split()[4]
        #print(ename)
        if ename == "IBCAD00CRCUR6" : 
            beamcurrent=emean
            beamcurrentsd=esd
        if ename == "RESET:i:GasPanelBarPress1" : 
            pmean=emean
            psd=esd
        if ename == "GAS:i::CDC_Temps-CDC_D1_Temp" :
            d1max=float(emax)
        if ename[:8] == "CDC:hv:A" and ename[12:15] == "imon" :
            tempsum=tempsum+float(emax)
        if ename == "CDC:hv:A:1:v0set" :
            hvset=emean
    
    if badepics ==1 :
        print("EPICS data is bad")
        return {"badepics":-1}

    else : 
    
        #print("EPICS data is good")

        d1max=d1max+273.15
        hvbi=0.125*float(tempsum)

        hvbi_scaled=hvbi
        if(isInit and def_hvbi<0):
            hvbi_scaled=-1*def_hvbi

        #print(def_hvbi)
        if def_hvbi != 0 and not isInit:
            p0 = -29.7807
            p1 = 0.0149823
            hvbi_2125 = def_hvbi    #2.05663
            #hvbi_scaled = float(hvbi)

            if hvset != 2125:
                hvbi_scaled = float(hvbi)*hvbi_2125/(p0+p1*float(hvset))

            if def_hvbi < 0 :
                hvbi_scaled = -1*def_hvbi

        #make a dictionary
        temperature=d1max
        if(def_temp<0):
            temperature=-1*def_temp

        pressure=pmean
        if(isInit and def_pressure<0):
            pressure=-1*def_pressure

        print("forming dictionary:", pmean,d1max,hvbi_scaled)
        model_in_dict={"pressure":float(pressure),"temp":float(temperature),"current":float(hvbi_scaled),"ideal_gcf":float(ideal_gcf)}
        #naomis_dict={"beam_curr":beamcurrent, "beam_curr_sd":beamcurrentsd, "pressure_mean":pmean, "pressure_sd":psd, "temp":d1max, "hvb_current":hvbi_scaled, "hvb_V":hvset}
        return  model_in_dict

def InitializeDefaults(config_file,init_lookback_time,model_name):
    #uses process epics fucntion to get the default values for the model in order to find the ideal gcf
    #it then writes the default values (as needed) to the config file

    gp_model, params = loadmodel.load_model(model_name)
    print(gp_model.kernel.get_params())

    print("loaded model:",model_name,":",gp_model)
    with open(config_file) as f:
        config = json.load(f)

    print("Initializing defaults...")
    getepics="myStats -b -"+str(init_lookback_time)+"s -l 'RESET:i:GasPanelBarPress1,IBCAD00CRCUR6,GAS:i::CDC_Temps-CDC_D1_Temp,CDC:hv:A:1:imon,CDC:hv:A:2:imon,CDC:hv:A:3:imon,CDC:hv:A:4:imon,CDC:hv:A:5:imon,CDC:hv:A:6:imon,CDC:hv:A:7:imon,CDC:hv:A:8:imon,CDC:hv:A:1:v0set' -u"
    print(getepics)
    p = Popen(getepics,stdin=PIPE,stdout=PIPE, stderr=PIPE,bufsize=-1,shell=True)
    epics_output, errors = p.communicate()


    
    input_dict=ProcessEPICS(epics_output,isInit=True,def_hvbi=config["default_hvbi"],def_temp=config["default_temp"],def_pressure=config["default_pressure"])

    print("init input dict",input_dict)
    if(config["default_pressure"]>=0):
        config["default_pressure"]=input_dict["pressure"]

    gcf, stdv,input_dict=runai.predict_gcf(gp_model,params,input_dict)

    if "badepics" in input_dict:
        print("bad epics data")
        return

    config["ideal_gcf"]=gcf
    if(config["default_hvbi"]>=0):
        config["default_hvbi"]=input_dict["current"]
    if(config["default_temp"]>=0):
        config["default_temp"]=input_dict["temp"]
    

    print("Writing new config file...")
    #print(config)
    #newconf=json.dumps(config, sort_keys=True, indent=4)
    with open(config_file,'w') as f:
        json.dump(config,f)

    return 

def calchv(ideal_gcf,model_pred_dict):
# read AI output and ideal gcf, and calculate recommended HV 

    gcf_expected=model_pred_dict['gcf']



    #TODO: scale ideal_gcf by the current HV setting
    gcfratio = (float(gcf_expected)/float(ideal_gcf))

    #2125V function
    #p0 = 1980.06   #  +/-   4.59519     
    #p1 = 196.163   #  +/-   8.8805      
    #p2 = -50.9084  #  +/-   4.22906 

    #2130V function
    p0            =   1980.06  #+/-  4.59519   
    p1            =   204.965  #+/-  9.27901   
    p2            =   -55.5798 # +/-  4.61713    

    newhv = p0 + p1*gcfratio + p2*gcfratio*gcfratio

    return newhv

def main(argv):
    """

    """
    #Arguments
    print("initializing AIEC_CDC")
    model_name=""
    poll_time=1 #minutes
    control_window=[2210.0,2250.0]
    ideal_gcf=0.141
    epics_trailing_window=15 #seconds
    config_file="./AIEC_CDC.cfg"
    require_human=0
    rec_scale=3
    time_out=0

    control_mask="ALL"

    waitforbeam=10 #seconds
    testing=False

    print("getting arguments")
    ap = argparse.ArgumentParser()

    ap.add_argument("-c", "--config", required=False,
    help="The config file")

    ap.add_argument("-I","--init",required=False,help="Initialize the hvbi and ideal gcf by looking back given number of seconds",default=0)

    args = vars(ap.parse_args())

    if args['config'] is not None:
        config_file=args['config']


    with open(config_file) as config_json:
        configuration=json.load(config_json)

    
    if int(args['init'])>0:
        print("initializing defaults with",args['init'],"seconds")
        InitializeDefaults(config_file,args["init"],configuration['model_name'])
        return

    print("checking for AIEC_CDC already running")
    AIEC_CDC_Running=False
    if(os.path.exists("/tmp/AIEC_CDC")):
        try:
            pidf=open("/tmp/AIEC_CDC","r")
            pid=pidf.readline().strip()
            print("Checking for process:", pid)

            pidf.close()
            os.kill(int(pid),0)
        except OSError:
            pass
        else:
            AIEC_CDC_Running=True
            getlastdatetime_q="SELECT MAX(Date) FROM GlueX_CDC"
            print("AIEC_CDC already running")
            print("zombie check:",getlastdatetime_q)
            ops_dbcursor.execute(getlastdatetime_q)
            last_datetime=ops_dbcursor.fetchall()[0]
            print("last datetime:",last_datetime)
            current_time = datetime.datetime.now() #2022-03-01 08:15:04
            last_time= last_datetime['MAX(Date)'] #time.strptime(last_datetime,"%Y-%m-%d %H:%M:%S")
            timedelta=(current_time-last_time).total_seconds()/60.0 #minutes
            if(timedelta>=2*poll_time):
                print("AIEC_CDC is running but last data was more than 2x poll time ago")
                AIEC_CDC_Running=False
                os.kill(int(pid),9)
            #check DB for too long if so kill it

    args = vars(ap.parse_args())

    print("Is already running? ", AIEC_CDC_Running)
    if(not AIEC_CDC_Running):
        pidf = open("/tmp/AIEC_CDC",'w')
        pidf.write(str(os.getpid()))
        pidf.close()

        print("Starting AIEC_CDC")

        #load model
        model_name=configuration["model_name"]
        old_model_name=model_name
        print("Loading model:"+model_name)
        gp_model, params = loadmodel.load_model(model_name)
        #print(gp_model.kernel.get_params())


        #check if params have changed (compare to DB)

        #write necessary values into variables for hv/GCF with uncertainties
        print("spawning control thread with",config_file,len(config_file))
        spawns=[]
        p=Process(target=ProcessRecommend, args=(config_file,))
        p.daemon = True
        spawns.append(p)
        spawns[0].start()

        #infinite loop
        loop_count=0
        print("starting main loop")
        while True: #loop_count<2:

            # Get the configurations from the config file
            print("Checking config")
            with open(config_file) as config_json:
                configuration=json.load(config_json)

            model_name=configuration["model_name"]

            if(model_name!=old_model_name):
                gp_model, params = loadmodel.load_model(model_name)
                old_model_name=model_name

            poll_time=configuration['poll_time'] #minutes
            control_window=configuration['control_window'] #[2210.0V,2250.0V]
            ideal_gcf=configuration['ideal_gcf'] #found in init, around .141
            epics_trailing_window=configuration['epics_trailing_window'] #15 #seconds
            require_human=configuration['require_human'] #should a human be in the loop
            rec_scale=configuration['rec_scale'] #of polls before recommendation
            def_hvbi=configuration['default_hvbi'] #9 uA
            def_temp=configuration['default_temp'] #K
            def_pressure=configuration['default_pressure'] # KPa
            control_mask=configuration['control_mask'] #string for cdc_tool.py of which boards to control e.g. 'ALL' or 'BRT,BRB'
            fail_safe_timeout=configuration['fail_safe_timeout'] #minutes to wait with EPICS being in a bad state until setting the HV to baseline 
            baseline_voltage=configuration['baseline_V'] #V nominal for the CDC and the fail_safe setpoint on timeout


            #read from epics
            print("Getting epics data...")
            getepics="myStats -b -"+str(epics_trailing_window)+"s -l 'RESET:i:GasPanelBarPress1,IBCAD00CRCUR6,GAS:i::CDC_Temps-CDC_D1_Temp,CDC:hv:A:1:imon,CDC:hv:A:2:imon,CDC:hv:A:3:imon,CDC:hv:A:4:imon,CDC:hv:A:5:imon,CDC:hv:A:6:imon,CDC:hv:A:7:imon,CDC:hv:A:8:imon,CDC:hv:A:1:v0set' -u"
            print(getepics)
            p = Popen(getepics,stdin=PIPE,stdout=PIPE, stderr=PIPE,bufsize=-1,shell=True)
            
            epics_output, errors = p.communicate()
            input_dict=ProcessEPICS(epics_output,def_hvbi,False,def_temp,def_pressure,ideal_gcf) #return as dictionary
            #run AI

            #print("PREDICTING:",gp_model, params,input_dict)
            gcf, stdv,input_dict=runai.predict_gcf(gp_model,params,input_dict)

            if "badepics" in input_dict:
                print("bad epics")
                insert_q="INSERT INTO GlueX_CDC (ModelName,InputDict,OutputDict,Recommend) VALUES (\"%s\",\"%s\",\"%s\",%i)" % (model_name,input_dict,{},0)
                print(insert_q)
                ops_dbcursor.execute(insert_q)
                ops_dbcnx.commit()
                if time_out==0:
                    time_out=time.time()
                else:
                    time_now=time.time()
                    if time_now-time_out>=fail_safe_timeout*60:
                        print("BAD EPICS TIMEOUT:",fail_safe_timeout,"minutes")
                        hvset_req="/group/halld/AIEC/utilities/cdc_tool.py --hvset "+control_mask+" "+str(baseline_voltage)
                        print(hvset_req)
                        insert_q="INSERT INTO GlueX_CDC (ModelName,InputDict,OutputDict,Recommend,Accepted) VALUES (\"%s\",\"%s\",\"%s\",%i,NOW())" % (model_name,input_dict,{'hv_set':baseline_voltage},0)
                        print(insert_q)
                        ops_dbcursor.execute(insert_q)
                        ops_dbcnx.commit()
                       
                time.sleep(poll_time*60)
                continue


            if time_out !=0:
                time_out=0

            output_dict={"gcf":gcf,"stdv":stdv}
            output_dict['hv_set']=calchv(ideal_gcf,output_dict)

            print("AI output:",output_dict)
            #write to DB (if req human=false write set flag automatically)
            do_rec=0
            if(loop_count%rec_scale==0):
                print("Recommending")
                do_rec=1

            insert_q="INSERT INTO GlueX_CDC (ModelName,InputDict,OutputDict,Recommend) VALUES (\"%s\",\"%s\",\"%s\",%i)" % (model_name,input_dict,output_dict,do_rec)
            print(insert_q)
            ops_dbcursor.execute(insert_q)
            ops_dbcnx.commit()

            #wait until poll time
            loop_count+=1
            time.sleep(poll_time*60)
            

    ops_dbcnx.close()

if __name__ == "__main__":
   main(sys.argv[1:])
