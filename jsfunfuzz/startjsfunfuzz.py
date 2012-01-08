#!/usr/bin/env python
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import platform
import subprocess
import sys
import time

from fnStartjsfunfuzz import verboseDump, hgHashAddToFuzzPath, cpJsTreeDir, autoconfRun, cfgJsBin, \
    compileCopy, cpUsefulFiles, archOfBinary, testDbgOrOptGivenACompileType

def main():

    # Variables
    selfTests = True
    multiTimedRunTimeout = '10'

    if os.name != 'nt' and os.uname()[4] == 'armv7l':
        if os.uname()[1] == 'tegra-ubuntu':
            multiTimedRunTimeout = '180'
        else:
            multiTimedRunTimeout = '600'

    traceJit = False  # Activate support for tracing JIT in configure.
    methodJit = True  # Activate support for method JIT in configure.
    methodJitSwitch = True  # Activate JIT fuzzing here.
    methodJitAllSwitch = True  # turn on -a
    debugJitSwitch = True  # turn on -d

    # Pymake is activated on Windows platforms by default, for default tip only.
    usePymake = True if os.name == 'nt' else False

    jsCompareJITSwitch = True
    # Disable compareJIT if methodJit support is disabled in configure.
    if not methodJitSwitch:
        jsCompareJITSwitch = False
    # Disable compareJIT for 1.9.2 branch.
    if sys.argv[3] == '192':
        jsCompareJITSwitch = False

    # Sets --enable-threadsafe for a multithreaded js shell, first make sure NSPR is installed!
    # (Use `make` instead of `gmake`), see https://developer.mozilla.org/en/NSPR_build_instructions
    threadsafe = False

    if os.name != 'nt' and (os.uname()[0] == "Linux" or os.uname()[0] == "Darwin"):
        # Enable creation of coredumps.
        verboseDump('Setting ulimit -c to unlimited..')
        subprocess.call(['ulimit -c unlimited'], shell=True)
        if os.uname()[0] == "Linux":
            # Only allow one process to create a coredump at a time.
            subprocess.call(['echo 1 | sudo tee /proc/sys/kernel/core_uses_pid'], shell=True)

    branchSuppList = []
    branchSuppList.append('192')
    branchSuppList.append('mc')
    branchSuppList.append('tm')
    branchSuppList.append('jm')
    branchSuppList.append('im')
    branchSuppList.append('mi')
    branchSuppList.append('larch')

    # There should be a minimum of 4 command-line parameters.
    if len(sys.argv) < 4:
        raise Exception('Too little command-line parameters.')

    # Check supported operating systems.
    if (sys.argv[1] == '64'):
        # 64-bit js shells have only been tested on Linux x86_64 (AMD64) platforms.
        if os.name != 'nt' and os.uname()[0] == 'Linux' and os.uname()[4] != 'x86_64':
            raise Exception('64-bit compilation is not supported on non-x86_64 Linux platforms.')

    archNum = sys.argv[1]
    assert int(archNum) in (32, 64)
    compileType = sys.argv[2]
    assert compileType in ('dbg', 'opt')
    branchType = sys.argv[3]
    assert branchType in branchSuppList

    valgrindSupport = False
    if (os.name == 'posix'):
        if (len(sys.argv) == 5 and sys.argv[4] == 'valgrind') or \
            (len(sys.argv) == 7 and sys.argv[6] == 'valgrind') or \
            (len(sys.argv) == 9 and sys.argv[8] == 'valgrind'):
            if (os.uname()[0] == 'Linux') or (os.uname()[0] == 'Darwin'):
                valgrindSupport = True
                # compareJIT is too slow..
                jsCompareJITSwitch = False  # Turn off compareJIT when in Valgrind.
                multiTimedRunTimeout = '300'  # Increase timeout to 300 in Valgrind.

    repoDict = {}
    pathSeparator = os.sep
    # Definitions of the different repository and fuzzing locations.
    # Remember to normalize paths to counter forward/backward slash issues on Windows.
    repoDict['fuzzing'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'fuzzing'))) + pathSeparator
    repoDict['192'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'mozilla-1.9.2'))) + pathSeparator
    repoDict['mc'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'mozilla-central'))) + pathSeparator
    repoDict['tm'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'tracemonkey'))) + pathSeparator
    repoDict['jm'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'jaegermonkey'))) + pathSeparator
    repoDict['im'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'ionmonkey'))) + pathSeparator
    repoDict['mi'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'mozilla-inbound'))) + pathSeparator
    repoDict['larch'] = os.path.normpath(os.path.expanduser(os.path.join('~', 'trees', 'larch'))) + pathSeparator
    # Start of fuzzing directory, does not need pathSeparator at the end.
    fuzzPathStart = os.path.normpath(os.path.expanduser(os.path.join('~', 'Desktop', 'jsfunfuzz-')))
    if os.name == 'nt' and 'Windows-XP' in platform.platform():
        raise Exception('Not supported on Windows XP.')
        # for repo in repoDict.keys():
            ## It is assumed that on WinXP, the corresponding directories are in the root folder.
            ## e.g. Instead of `~/tracemonkey/`, TM would be in `/tracemonkey/`.
            # repoDict[repo] = repoDict[repo][1:]
        # fuzzPathStart = '/jsfunfuzz-'  # Start of fuzzing directory

    for repo in repoDict.keys():
        verboseDump('The directory for the "' + repo + '" repository is "' + repoDict[repo] + '"')

    fuzzPath = fuzzPathStart + compileType + '-' + archNum + '-' + branchType + pathSeparator
    if 'Windows-XP' not in platform.platform():
        fuzzPath = os.path.expanduser(fuzzPath)  # Expand the ~ folder except on WinXP.

    # Save the current directory as a variable.
    currDir = os.getcwd()

    # Note and attach the numbers and hashes of the current changeset in the fuzzPath.
    if 'Windows-XP' not in platform.platform():
        try:
            os.chdir(os.path.expanduser(repoDict[branchType]))
        except OSError:
            raise Exception('The directory for "' + branchType + '" is not found.')
        (fuzzPath, onDefaultTip) = hgHashAddToFuzzPath(fuzzPath, currWorkingDir=os.path.expanduser(repoDict[branchType]))
        os.chdir(os.path.expanduser(currDir))
    else:
        try:
            os.chdir(repoDict[branchType])
        except OSError:
            raise Exception('The directory for "' + branchType + '" is not found.')
        (fuzzPath, onDefaultTip) = hgHashAddToFuzzPath(fuzzPath, currWorkingDir=repoDict[branchType])
        os.chdir(currDir)

    # Turn off pymake if not on default tip.
    if usePymake and not onDefaultTip:
        usePymake = False

    # Raise an exception if not on default tip on Windows.
    if os.name == 'nt' and not onDefaultTip:
        raise Exception('Only default tip is supported on Windows platforms for the moment.')

    # Create the fuzzing folder.
    try:
        # Rename directory if patches are applied, accept up to 2 patches.
        if len(sys.argv) >= 6 and (sys.argv[4] == 'patch' or sys.argv[6] == 'patch'):
            fuzzPath = os.path.join(fuzzPath, 'patched')
            verboseDump('Patched fuzzPath is: ' + fuzzPath)
        #os.makedirs(fuzzPath)
    except OSError:
        raise Exception("The fuzzing path at '" + fuzzPath + "' already exists!")

    # Copy the js tree to the fuzzPath.
    compilePath = os.path.join(fuzzPath, 'compilePath', 'js', 'src')
    cpJsTreeDir(repoDict[branchType], compilePath, 'jsSrcDir')
    if os.path.isdir(os.path.normpath(os.path.join(repoDict[branchType], 'js', 'public'))):
        cpJsTreeDir(repoDict[branchType], os.path.join(compilePath, '..', 'public'), 'jsPublicDir')
    if os.path.isdir(os.path.normpath(os.path.join(repoDict[branchType], 'mfbt'))):
        cpJsTreeDir(repoDict[branchType], os.path.join(compilePath, '..', '..', 'mfbt'), 'mfbtDir')
    os.chdir(compilePath)  # Change into compilation directory.

    # Patch the codebase if specified, accept up to 2 patches.
    # FIXME: Replace this with `hg qimport`.
    patchReturnCode = 0
    patchReturnCode2 = 0
    if len(sys.argv) < 8 and len(sys.argv) >= 6 and sys.argv[4] == 'patch':
        patchReturnCode = subprocess.call(['patch', '-p3', '-i', sys.argv[5]])
        verboseDump('Finished incorporating the first patch.')
    elif len(sys.argv) >= 8 and sys.argv[6] == 'patch':
        patchReturnCode = subprocess.call(['patch', '-p3', '-i', sys.argv[5]])
        verboseDump('Finished incorporating the first patch.')
        patchReturnCode2 = subprocess.call(['patch', '-p3', '-i', sys.argv[7]])
        verboseDump('Finished incorporating the second patch.')
    if (patchReturnCode == 1 or patchReturnCode2 == 1) or (patchReturnCode == 2 or patchReturnCode2 == 2):
        raise Exception('Patching failed.')

    # FIXME we should make startjsfunfuzz.py not rely on os.getcwdu(), instead run subprocess calls
    # with the required directory set. In short, stop jumping around directories.
    autoconfRun(compilePath)

    # Create objdirs within the compilePaths.
    objdir = os.path.join(compilePath, compileType + '-objdir')
    os.mkdir(objdir)
    # Compile the other shell.
    if compileType == 'dbg':
        objdir2 = os.path.join(compilePath, 'opt-objdir')
    elif compileType == 'opt':
        objdir2 = os.path.join(compilePath, 'dbg-objdir')
    os.mkdir(objdir2)
    os.chdir(objdir)

    # Compile the first binary.
    cfgJsBin(archNum, compileType, threadsafe, os.path.join(compilePath, 'configure'), objdir)

    # Compile and copy the first binary.
    jsShellName = compileCopy(archNum, compileType, branchType, usePymake, fuzzPath, objdir, valgrindSupport)
    # Change into compilePath/js/src/ for the second binary.
    os.chdir('../')

    # Test compilePath.
    verboseDump('This should be the compilePath/js/src:')
    verboseDump('%s\n' % os.getcwdu())
    if selfTests:
        if 'src' not in os.getcwdu():
            raise Exception('We are not in src.')

    # Re-run autoconf again.
    autoconfRun(compilePath)

    # Compile the other binary.
    # No need to assign jsShellName here, because we are not fuzzing this one.
    if compileType == 'dbg':
        os.chdir('opt-objdir')
        cfgJsBin(archNum, 'opt', threadsafe, os.path.join(compilePath, 'configure'), objdir2)
        compileCopy(archNum, 'opt', branchType, usePymake, fuzzPath, objdir2, valgrindSupport)
    elif compileType == 'opt':
        os.chdir('dbg-objdir')
        cfgJsBin(archNum, 'dbg', threadsafe, os.path.join(compilePath, 'configure'), objdir2)
        compileCopy(archNum, 'dbg', branchType, usePymake, fuzzPath, objdir2, valgrindSupport)

    os.chdir('../../../../')  # Change into fuzzPath directory.

    # Test fuzzPath.
    verboseDump('os.getcwdu() should be the fuzzPath:')
    verboseDump(os.getcwdu() + str(pathSeparator))
    verboseDump('fuzzPath is: %s\n' % fuzzPath)
    if selfTests:
        if os.name == 'posix': # temporarily disable this since this doesn't yet work with the new os.path.join stuff
            if fuzzPath != (os.getcwdu()):
                raise Exception('We are not in fuzzPath.')
        elif os.name == 'nt':
            pass  # temporarily disable this since this doesn't yet work with the new os.path.join stuff
            #if fuzzPath[1:] != (os.getcwdu() + '/')[3:]:  # Ignore drive letter.
                #raise Exception('We are not in fuzzPath.')

    # Copy over useful files that are updated in hg fuzzing branch.
    cpUsefulFiles(os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('jsfunfuzz', 'jsfunfuzz.js')))
    cpUsefulFiles(os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('jsfunfuzz', 'analysis.py')))
    cpUsefulFiles(os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('jsfunfuzz', 'runFindInterestingFiles.py')))
    cpUsefulFiles(os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('jsfunfuzz', '4test.py')))

    jsknownDict = {}
    # Define the corresponding js-known directories.
    jsknownDict['192'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-1.9.2')) + pathSeparator
    jsknownDict['mc'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator
    # For TM and JM, we use mozilla-central's js-known directories.
    jsknownDict['tm'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator
    jsknownDict['jm'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator
    jsknownDict['im'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator
    jsknownDict['mi'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator
    jsknownDict['larch'] = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('js-known', 'mozilla-central')) + pathSeparator

    multiTimedRun = os.path.normpath(repoDict['fuzzing'] + os.sep + os.path.join('jsfunfuzz', 'multi_timed_run.py'))

    # FIXME: --random-flags can be done in a better way instead of appending here
    if jsCompareJITSwitch:
        jsCompareJIT = ' --comparejit --random-flags'
    else:
        jsCompareJIT = ' --random-flags'

    if branchType == 'mc':
        jsCompareJIT += ' --repo=' + repoDict['mc']
    if branchType == 'jm':
        jsCompareJIT += ' --repo=' + repoDict['jm']
    if branchType == 'im':
        jsCompareJIT += ' --repo=' + repoDict['im']
    if branchType == 'mi':
        jsCompareJIT += ' --repo=' + repoDict['mi']
    if branchType == 'larch':
        jsCompareJIT += ' --repo=' + repoDict['larch']

    if methodJitSwitch:
        jsMethodJit = ' -m -n '
        if methodJitAllSwitch:
            jsMethodJit = ' -m -n -a '
    else:
        jsMethodJit = ''

    # FIXME: This can be done in a better way instead of appending to jsMethodJit
    if debugJitSwitch and branchType != 'im':
        jsMethodJit += '-d '
    # Thanks to decoder and sstangl, useful flag combinations are:
    # {{--ion -n, --ion, --ion-eager} x {--ion-regalloc=greedy, --ion-regalloc=lsra}}
    if branchType == 'im':
        # Actually these flags should be random within multi timed run, not in startjsfunfuzz
        #rndIntIM = randint(0,5)  # randint comes from the random module.
        # Start off with ion-eager.
        # --random-flags might treat --ion -n as 2 flags, which should not be the case.
        rndIntIM = 5
        if rndIntIM == 0:
            jsMethodJit += '--ion -n --ion-regalloc=greedy '
        elif rndIntIM == 1:
            jsMethodJit += '--ion --ion-regalloc=greedy '
        elif rndIntIM == 2:
            jsMethodJit += '--ion-eager --ion-regalloc=greedy '
        elif rndIntIM == 3:
            jsMethodJit += '--ion -n --ion-regalloc=lsra '
        elif rndIntIM == 4:
            jsMethodJit += '--ion --ion-regalloc=lsra '
        elif rndIntIM == 5:
            jsMethodJit += '--ion-eager --ion-regalloc=lsra '

    # Commands to simulate bash's `tee`.
    tee = subprocess.Popen(['tee', 'log-jsfunfuzz'], stdin=subprocess.PIPE)

    # Define fuzzing command with the required parameters.
    if 'Windows-XP' not in platform.platform():
        multiTimedRun = os.path.expanduser(multiTimedRun)
        jsknownDict[branchType] = os.path.expanduser(jsknownDict[branchType])
    fuzzCmd1 = 'python -u ' + multiTimedRun + jsCompareJIT
    if valgrindSupport:
        fuzzCmd1 = fuzzCmd1 + ' --valgrind'
    fuzzCmd = fuzzCmd1 + ' ' + multiTimedRunTimeout + ' ' + jsknownDict[branchType] + ' ' + jsShellName + jsMethodJit

    verboseDump('jsShellName is: ' + jsShellName)
    verboseDump('fuzzPath + jsShellName is: ' + jsShellName)
    if os.name == 'nt':
        print('fuzzCmd is: ' + fuzzCmd.replace('\\', '\\\\') + '\n')
    else:
        print('fuzzCmd is: ' + fuzzCmd + '\n')

    # 32-bit or 64-bit verification test.
    if (os.name == 'posix'):
        if (os.uname()[0] == 'Linux') or (os.uname()[0] == 'Darwin'):
            assert archOfBinary(jsShellName) == archNum

    # Debug or optimized binary verification test.
    testDbgOrOptGivenACompileType(jsShellName, compileType)

    print '''
    ================================================
    !  Fuzzing %s %s %s js shell builds now  !
       DATE: %s
    ================================================
    ''' % (archNum + '-bit', compileType, branchType, time.asctime( time.localtime(time.time()) ))

    # Commands to simulate bash's `tee`.
    # Start fuzzing the newly compiled builds.
    subprocess.call(fuzzCmd, stdout=tee.stdin, shell=True)

# Run main when run as a script, this line means it will not be run as a module.
if __name__ == '__main__':
    main()
