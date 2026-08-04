#!/usr/bin/env python
# USAGE: /test/submit_digi.py -a 0.021 -l 1350 -o out_giulia_cu -i /cnaf/cygno-sim/Users/dimarcoe/digitune/digi_giulia_cu -s users/dimarcoe/digi/cu_giulia $PWD
import os, sys, re
import numpy as np
from pathlib import Path

ENDPOINT_URL='https://s3.cr.cnaf.infn.it:7480/'

jobstring  = '''#!/bin/bash
ulimit -c 0 -S
ulimit -c 0 -H
set -e

# Experiment executable config
export CVMFS_PARENT_DIR=""
source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-ubuntu2204-gcc11-opt/setup.sh
source /cvmfs/sft-cygno.infn.it/config/setup_digi.sh
'''

def makeInputList(inputdir):
    inputcloud = re.sub(r'^.*?(?=cygno-)', '', inputdir)
    inputcloud = os.path.normpath(inputcloud)
    full_url = f"{ENDPOINT_URL}cygno:{inputcloud}"
    full_url = re.sub(r'(?<!:)/{2,}', '/', full_url) # remove eventual last // wich prevents wget from cloud
    wget_cmds = []
    for file in Path(inputdir).glob("*.root"):
        if file.is_file():
            wget_cmds.append(f"wget {full_url}/{file.name}")
    copy_cmd = '\n'.join(wget_cmds)
    print(f"Will copy the input files: {copy_cmd} over cloud in the jobs itself.")
    return copy_cmd

def makePreSign(jobdir,outdir,outfile,options):
    BUCKET=options.bucket
    TAG=f'{options.storagedir}/{outdir}/'
    FILETOKEN="/tmp/token"
    
    print(f"generating presigned url for: {outfile}.root with command: presigned.py -u {ENDPOINT_URL} -b {BUCKET} -t {TAG} {outfile}.root -f {FILETOKEN} > {jobdir}/{outdir}/{outfile}.json")
    os.system(f"/cvmfs/sft-cygno.infn.it/config/lib/presigned.py -u {ENDPOINT_URL} -b {BUCKET} -t {TAG} {outfile}.root -f {FILETOKEN} > {jobdir}/{outdir}/{outfile}.json")

def makeCondorFile(jobdir, srcFiles, cfgFiles, outFiles, nrootfiles, options, logdir, errdir, outdirCondor):

    dummy_exec = open(jobdir+'/dummy_exec.sh','w')
    dummy_exec.write('#!/bin/bash\n')
    dummy_exec.write('bash $*\n')
    dummy_exec.close()
     
    condor_file_name = jobdir+'/condor_submit.condor'
    condor_file = open(condor_file_name,'w')
    condor_file.write('''+SingularityImage = "/cvmfs/sft-cygno.infn.it/dockers/images/cygno-wn_v2.4.sif"
+SingularityBind = "/cvmfs/:/cvmfs/"
Requirements = HasSingularity

Executable = {de}
Log        = {ld}/$(ProcId).log
Output     = {od}/$(ProcId).out
Error      = {ed}/$(ProcId).error
getenv      = True
next_job_start_delay = 1
environment = "LS_SUBCWD={here}"
request_cpus = {cpu}
should_transfer_files   = YES
preserve_relative_paths = True
+CygnoUser = "{user}"\n
'''.format(de=dummy_exec.name,
           ld=os.path.abspath(logdir), od=os.path.abspath(outdirCondor),ed=os.path.abspath(errdir),
           cpu=options.threads, user=os.environ['USERNAME'], here=os.environ['PWD'] ) )
    for i,sf in enumerate(srcFiles):
        outdir = os.path.splitext(outFiles[i])[0]
        print (f"isrcfile = {i}, sf={sf}, outdir={outdir}")
        # create the json files for the transfer (1/output file)
        jsonfiles = []
        for run in range(1,nrootfiles+1):
            rfile=f"histograms_Run{run:05d}"
            makePreSign(outdirCondor,outdir,rfile,options)
            jsonfiles.append(f"{outdirCondor}/{outdir}/{rfile}.json")
        jsonstring = ", ".join(jsonfiles)
        condor_file.write(f'transfer_input_files = {os.path.abspath(options.srcdir)}/build-dir, {os.path.abspath(options.srcdir)}/VignettingMap, {os.path.abspath(cfgFiles[i])}, {os.path.abspath(sf)}, /cvmfs/sft-cygno.infn.it/config/lib/s3upload_put.py, {jsonstring}\n')
        #condor_file.write(f'transfer_output_files = \n')
        condor_file.write(f'arguments = {os.path.basename(sf)} \nqueue \n\n')
        
    condor_file.close()
    return condor_file_name

def replaceParam(input_file,old_string,new_string,output_file=None):
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = [line.replace(old_string, new_string) for line in lines]

    if not output_file:
        output_file = input_file
    with open(output_file, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print(f"Replaced {old_string} with {new_string} in {output_file}")

if __name__ == "__main__":

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("srcdir", help="base directory where build-dir is")
    parser.add_argument("-a", "--alphas", type=float, nargs="*",  default=np.linspace(0.019,0.023,11), help="List of alpha values to scan (default: %(default)s)")
    parser.add_argument("-l", "--lambdas", type=float, nargs="*",  default=np.linspace(850,1850,11), help="List of absorption length values (in mm) to scan (default: %(default)s)")
    parser.add_argument("-c", "--ce", type=int, default=2, help="Computing element in condor to use")
    parser.add_argument("-t", "--threads", type=int, default=8, help="Number of CPUs to request")
    parser.add_argument("-o", "--outdir", type=str, default=None, help='output directory');
    parser.add_argument("-i", "--inputdir", type=str, default=None, help='input directory');
    parser.add_argument("-b", "--bucket", type=str, default="cygno-analysis", help='bucket in the cloud where to store the output (default: %(default)s)');
    parser.add_argument("-s", "--storagedir", type=str, default="users/dimarcoe/digi/fe_zcone", help='output directory in the cloud (default: %(default)s)');
    args = parser.parse_args()

    print("SUBMIT DIGI")
    absopath  = os.path.abspath(args.outdir)
    if not args.outdir:
        raise RuntimeError ('ERROR: give at least an output directory. there will be a HUGE number of jobs!')
    else:
        if not os.path.isdir(absopath):
            print ('making a directory and running in it')
            os.system('mkdir -p {od}'.format(od=absopath))

    if not args.inputdir.startswith("/cnaf/cygno-"):
        raise RuntimeError ('ERROR: inputdir should start with "/cnaf/cygno-" because the job copies the inputfiles from cloud with wget fro the 3 allowed cygno-<bucket>s')
    else:
        number_root_outfiles = sum(1 for file in Path(args.inputdir).glob("*.root") if file.is_file()) 
        print(f"==> Each DIGI job will run on {number_root_outfiles} input ROOT files and produce the same number of output files")
        
    jobdir = absopath+'/jobs/'
    if not os.path.isdir(jobdir):
        os.system('mkdir -m 777 -p {od}'.format(od=jobdir))
    logdir = absopath+'/logs/'
    if not os.path.isdir(logdir):
        os.system('mkdir -m 777 -p {od}'.format(od=logdir))
    errdir = absopath+'/errs/'
    if not os.path.isdir(errdir):
        os.system('mkdir -m 777 -p {od}'.format(od=errdir))
    outdirCondor = absopath+'/outs/'
    if not os.path.isdir(outdirCondor):
        os.system('mkdir -m 777 -p {od}'.format(od=outdirCondor))

    srcfiles,cfgfiles,outfiles = [],[],[]
    for a,alpha in enumerate(args.alphas):
        for l,Lambda in enumerate(args.lambdas):
            print (f"Prepare job for pair (alpha,Lambda) = ({alpha},{Lambda})")
            con_file_name = jobdir+f"/conf_{a}-{l}.txt"
            os.system(f"cp {args.srcdir}/config/ConfigFile_new.txt {con_file_name}") 
            job_file_name = jobdir+f"/job_{a}-{l}.sh"
            log_file_name = logdir+f"/job_{a}-{l}.sh"
            tmp_file = open(job_file_name, 'w')

            replaceParam(con_file_name,"'absorption_l'          : 1350.",  f"'absorption_l'          : {Lambda:.0f}")
            replaceParam(con_file_name,"'alpha_G'               : 0.0209", f"'alpha_G'               : {alpha:.3f}")
            #replaceParam(con_file_name,"'events'                : -1",f"'events'                : 10")
            
            os.system(f'mkdir -m 777 -p {outdirCondor}/digi_{a}-{l}')
            outfiles.append(f'digi_{a}-{l}')

            tmp_filecont = jobstring
            # N.B.: use explicitly "./" as the directory for the config file name, because the path for the vignetting is built from there in DigitizationRunner.cxx
            cmd = f"\n./build-dir/digitizationpp ./{os.path.basename(con_file_name)} -I ./ -O digi_{a}-{l}"

            tmp_filecont += makeInputList(args.inputdir)
            tmp_filecont += cmd
            for run in range(1,number_root_outfiles+1):
                jsonfile=f"histograms_Run{run:05d}.json"
                tmp_filecont += f"\n./s3upload_put.py {jsonfile}"
            tmp_filecont += "\necho DONE.\n"
            tmp_file.write(tmp_filecont)
            tmp_file.close()
            srcfiles.append(job_file_name)
            cfgfiles.append(con_file_name)
    cf = makeCondorFile(jobdir,srcfiles,cfgfiles,outfiles,number_root_outfiles,args,logdir,errdir,outdirCondor)
    subcmd = f'source $CVMFS_PARENT_DIR/cvmfs/sft-cygno.infn.it/config/cygno_htc -s {cf} {args.ce}'

    print (subcmd)

    sys.exit()
    
