#!/usr/bin/env python
import os, sys
import numpy as np

jobstring  = '''#!/bin/bash
ulimit -c 0 -S
ulimit -c 0 -H
set -e

# Experiment executable config
export CVMFS_PARENT_DIR=""
source /cvmfs/sft.cern.ch/lcg/views/LCG_105/x86_64-ubuntu2204-gcc11-opt/setup.sh
source /cvmfs/sft-cygno.infn.it/config/setup_digi.sh
COMMAND
'''


def makeCondorFile(jobdir, srcFiles, cfgFiles, outFiles, options, logdir, errdir, outdirCondor):

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
        condor_file.write(f'transfer_input_files = {os.path.abspath(options.srcdir)}/build-dir,{os.path.abspath(options.srcdir)}/VignettingMap,{os.path.abspath(cfgFiles[i])},{os.path.abspath(options.inputdir)},{os.path.abspath(sf)} \n')
        condor_file.write(f'transfer_output_files = {os.path.splitext(outFiles[i])[0]}\n')
        if options.storagedir:
            condor_file.write(f'transfer_output_remaps = "{os.path.splitext(outFiles[i])[0]} = {options.storagedir}/{os.path.splitext(outFiles[i])[0]}"\n')
        else:
            condor_file.write(f'transfer_output_remaps = "{os.path.splitext(outFiles[i])[0]} = {outdirCondor}/{os.path.splitext(outFiles[i])[0]}"\n')
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
    parser.add_argument("-s", "--storagedir", type=str, default=None, help='output directory for the data (if null, use local outdir)');
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
    if not args.storagedir:
        outdirStorage = outdirCondor
    else:
        outdirStorage = os.path.abspath(args.storagedir)

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
            
            targetDir = outdirCondor if not args.storagedir else outdirStorage
            tmp_filecont = jobstring
            # N.B.: use explicitly "./" as the directory for the config file name, because the path for the vignetting is built from there in DigitizationRunner.cxx
            cmd = f"./build-dir/digitizationpp ./{os.path.basename(con_file_name)} -I {os.path.basename(os.path.normpath(args.inputdir))} -O digi_{a}-{l}"
            tmp_filecont = tmp_filecont.replace('COMMAND',cmd)
            tmp_file.write(tmp_filecont)
            tmp_file.close()
            srcfiles.append(job_file_name)
            cfgfiles.append(con_file_name)
            os.system(f'mkdir -m 777 -p {targetDir}/digi_{a}-{l}')
            outfiles.append(f'digi_{a}-{l}')
    cf = makeCondorFile(jobdir,srcfiles,cfgfiles,outfiles,args,logdir,errdir,outdirCondor)
    subcmd = f'source $CVMFS_PARENT_DIR/cvmfs/sft-cygno.infn.it/config/cygno_htc -s {cf} {args.ce}'

    print (subcmd)

    sys.exit()
    
