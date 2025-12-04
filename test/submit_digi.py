#!/usr/bin/env python
import os, sys

jobstring  = '''#!/bin/sh
ulimit -c 0 -S
ulimit -c 0 -H
set -e
export CE=2
export IMAGE="/cvmfs/sft-cygno.infn.it/dockers/images/cygno-wn_v2.4.sif"

# Experimet executable config
source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-ubuntu2204-gcc11-opt/setup.sh
source /cvmfs/sft-cygno.infn.it/config/setup_digi.sh
cd WORKDIR
COMMAND
source $CVMFS_PARENT_DIR/cvmfs/sft-cygno.infn.it/config/cygno_htc -s  $CE
'''


def makeCondorFile(jobdir, srcFiles, options, logdir, errdir, outdirCondor):

    dummy_exec = open(jobdir+'/dummy_exec.sh','w')
    dummy_exec.write('#!/bin/bash\n')
    dummy_exec.write('bash $*\n')
    dummy_exec.close()
     
    condor_file_name = jobdir+'/condor_submit.condor'
    condor_file = open(condor_file_name,'w')
    condor_file.write('''Universe = vanilla
Executable = {de}
Log        = {ld}/$(ProcId).log
Output     = {od}/$(ProcId).out
Error      = {ed}/$(ProcId).error
getenv      = True
next_job_start_delay = 1
environment = "LS_SUBCWD={here}"
request_cpus = {cpu}
+CygnoUser = "{user}"\n
'''.format(de=os.path.abspath(dummy_exec.name), ld=os.path.abspath(logdir), od=os.path.abspath(outdirCondor),ed=os.path.abspath(errdir),
               cpu=options.threads, user=os.environ['USERNAME'], here=os.environ['PWD'] ) )
    for sf in srcFiles:
        condor_file.write(f'arguments = {os.path.abspath(sf)} \nqueue 1 \n\n')
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
    parser.add_argument("executable", help="digitization exe file")
    parser.add_argument("config", help="digitization config file")
    parser.add_argument("-a", "--alphas", type=float, nargs="*",  default=[0.01, 0.02, 0.03], help="List of alpha values to scan (default: %(default)s)")
    parser.add_argument("-g", "--gains", type=float, nargs="*",  default=[0.02, 0.03, 0.04], help="List of gain normalization values to scan (default: %(default)s)")
    parser.add_argument("-t", "--threads", type=int, default=8, help="Number of CPUs to request")
    parser.add_argument("-o", "--outdir", type=str, default=None, help='output directory');
    parser.add_argument("-i", "--inputdir", type=str, default=None, help='input directory');
    args = parser.parse_args()

    print("SUBMIT DIGI")
    absopath  = os.path.abspath(args.outdir)
    if not args.outdir:
        raise RuntimeError ('ERROR: give at least an output directory. there will be a HUGE number of jobs!')
    else:
        if not os.path.isdir(absopath):
            print ('making a directory and running in it')
            os.system('mkdir -p {od}'.format(od=absopath))
    
    jobdir = absopath+'/jobs/'
    if not os.path.isdir(jobdir):
        os.system('mkdir {od}'.format(od=jobdir))
    logdir = absopath+'/logs/'
    if not os.path.isdir(logdir):
        os.system('mkdir {od}'.format(od=logdir))
    errdir = absopath+'/errs/'
    if not os.path.isdir(errdir):
        os.system('mkdir {od}'.format(od=errdir))
    outdirCondor = absopath+'/outs/'
    if not os.path.isdir(outdirCondor):
        os.system('mkdir {od}'.format(od=outdirCondor))
    basedigidir = os.path.abspath(args.executable).split('build-dir')[0]
    os.system(f"cp -r {basedigidir}/VignettingMap {jobdir}")

    srcfiles = []
    for a,alpha in enumerate(args.alphas):
        for g,gain in enumerate(args.gains):
            print (f"Prepare job for pair (alpha,normgain) = ({alpha},{gain})")
            con_file_name = jobdir+f"/conf_{a}-{g}.txt"
            os.system(f"cp {args.config} {con_file_name}") 
            job_file_name = jobdir+f"/job_{a}-{g}.sh"
            log_file_name = logdir+f"/job_{a}-{g}.sh"
            tmp_file = open(job_file_name, 'w')

            replaceParam(con_file_name,"'c_G'                   : 0.03",  f"'c_G'                   : {gain:.3f}")
            replaceParam(con_file_name,"'alpha_G'               : 0.0209",f"'alpha_G'               : {alpha:.3f}")
            
            tmp_filecont = jobstring
            tmp_filecont = tmp_filecont.replace('WORKDIR',jobdir)
            # N.B.: use explicitly "./" as the directory for the config file name, because the path for the vignetting is built from there in DigitizationRunner.cxx
            cmd = f"{os.path.abspath(args.executable)} ./{os.path.basename(con_file_name)} -I {os.path.abspath(args.inputdir)} -O {os.path.abspath(args.outdir)}/digi_{a}-{g}/"
            tmp_filecont = tmp_filecont.replace('COMMAND',cmd)
            tmp_file.write(tmp_filecont)
            tmp_file.close()
            srcfiles.append(job_file_name)
    cf = makeCondorFile(jobdir,srcfiles,args,logdir,errdir,outdirCondor)
    subcmd = f'source $CVMFS_PARENT_DIR/cvmfs/sft-cygno.infn.it/config/cygno_htc -s {cf} 2'

    print (subcmd)

    sys.exit()
    
