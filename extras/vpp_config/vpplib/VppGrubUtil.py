# Copyright (c) 2016 Cisco and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""VPP Grub Utility Library."""

import re

from vpplib.VPPUtil import VPPUtil

__all__ = ['VppGrubUtil']


class VppGrubUtil(object):
    """ VPP Grub Utilities."""

    def _get_current_cmdline(self):
        """
        Using /proc/cmdline return the current grub cmdline

        :returns: The current grub cmdline
        :rtype: string
        """

        # Get the memory information using /proc/meminfo
        cmd = 'sudo cat /proc/cmdline'
        (ret, stdout, stderr) = VPPUtil.exec_command(cmd)
        if ret != 0:
            raise RuntimeError(f"{cmd} on node {self._node['host']} {stdout} {stderr}")

        self._current_cmdline = stdout.strip('\n')

    def _get_default_cmdline(self):
        """
        Using /etc/default/grub return the default grub cmdline

        :returns: The default grub cmdline
        :rtype: string
        """

        # Get the default grub cmdline
        rootdir = self._node['rootdir']
        gfile = self._node['cpu']['grub_config_file']
        grubcmdline = self._node['cpu']['grubcmdline']
        cmd = f'cat {rootdir + gfile}'
        (ret, stdout, stderr) = VPPUtil.exec_command(cmd)
        if ret != 0:
            raise RuntimeError(
                f"{cmd} Executing failed on node {self._node['host']} {stderr}"
            )


        # Get the Default Linux command line, ignoring commented lines
        lines = stdout.split('\n')
        for line in lines:
            if line == '' or line[0] == '#':
                continue
            if ldefault := re.findall(f'{grubcmdline}=.+', line):
                self._default_cmdline = ldefault[0]
                break

    def get_current_cmdline(self):
        """
        Returns the saved grub cmdline

        :returns: The saved grub cmdline
        :rtype: string
        """
        return self._current_cmdline

    def get_default_cmdline(self):
        """
        Returns the default grub cmdline

        :returns: The default grub cmdline
        :rtype: string
        """
        return self._default_cmdline

    def create_cmdline(self, isolated_cpus):
        """
        Create the new grub cmdline

        :param isolated_cpus: The isolated cpu string
        :type isolated_cpus: string
        :returns: The command line
        :rtype: string
        """
        grubcmdline = self._node['cpu']['grubcmdline']
        cmdline = self._default_cmdline
        value = cmdline.split(f'{grubcmdline}=')[1]
        value = value.rstrip('"').lstrip('"')

        if isolcpus := re.findall(r'isolcpus=[\w+\-,]+', value):
            value = (
                re.sub(r'isolcpus=[\w+\-,]+', f'isolcpus={isolated_cpus}', value)
                if isolated_cpus != ''
                else re.sub(r'isolcpus=[\w+\-,]+', '', value)
            )

        elif isolated_cpus != '':
            value = f"{value} isolcpus={isolated_cpus}"
        if nohz := re.findall(r'nohz_full=[\w+\-,]+', value):
            value = (
                re.sub(r'nohz_full=[\w+\-,]+', f'nohz_full={isolated_cpus}', value)
                if isolated_cpus != ''
                else re.sub(r'nohz_full=[\w+\-,]+', '', value)
            )

        elif isolated_cpus != '':
            value = f"{value} nohz_full={isolated_cpus}"
        if rcu := re.findall(r'rcu_nocbs=[\w+\-,]+', value):
            value = (
                re.sub(r'rcu_nocbs=[\w+\-,]+', f'rcu_nocbs={isolated_cpus}', value)
                if isolated_cpus != ''
                else re.sub(r'rcu_nocbs=[\w+\-,]+', '', value)
            )

        elif isolated_cpus != '':
            value = f"{value} rcu_nocbs={isolated_cpus}"
        value = value.lstrip(' ').rstrip(' ')
        cmdline = f'{grubcmdline}="{value}"'
        return cmdline

    def apply_cmdline(self, node, isolated_cpus):
        """
        Apply cmdline to the default grub file

        :param node: Node dictionary with cpuinfo.
        :param isolated_cpus: The isolated cpu string
        :type node: dict
        :type isolated_cpus: string
        :return The vpp cmdline
        :rtype string
        """

        vpp_cmdline = self.create_cmdline(isolated_cpus)
        if len(vpp_cmdline):
            # Update grub
            # Save the original file
            rootdir = node['rootdir']
            grubcmdline = node['cpu']['grubcmdline']
            ofilename = rootdir + node['cpu']['grub_config_file'] + '.orig'
            filename = rootdir + node['cpu']['grub_config_file']

            # Write the output file
            # Does a copy of the original file exist, if not create one
            (ret, stdout, stderr) = VPPUtil.exec_command(f'ls {ofilename}')
            if ret != 0 and stdout.strip('\n') != ofilename:
                cmd = f'sudo cp {filename} {ofilename}'
                (ret, stdout, stderr) = VPPUtil.exec_command(cmd)
                if ret != 0:
                    raise RuntimeError(f"{cmd} failed on node {self._node['host']} {stderr}")

            # Get the contents of the current grub config file
            cmd = f'cat {filename}'
            (ret, stdout, stderr) = VPPUtil.exec_command(cmd)
            if ret != 0:
                raise RuntimeError(f"{cmd} failed on node {self._node['host']} {stderr}")

            # Write the new contents
            # Get the Default Linux command line, ignoring commented lines
            content = ""
            lines = stdout.split('\n')
            for line in lines:
                if line == '':
                    content += line + '\n'
                    continue
                if line[0] == '#':
                    content += line + '\n'
                    continue

                if ldefault := re.findall(f'{grubcmdline}=.+', line):
                    content += vpp_cmdline + '\n'
                else:
                    content += line + '\n'

            content = content.replace(r"`", r"\`")
            content = content.rstrip('\n')
            cmd = "sudo cat > {0} << EOF\n{1}\n".format(filename, content)
            (ret, stdout, stderr) = VPPUtil.exec_command(cmd)
            if ret != 0:
                raise RuntimeError(f"{cmd} failed on node {self._node['host']} {stderr}")

        return vpp_cmdline

    def __init__(self, node):
        distro = VPPUtil.get_linux_distro()
        if distro[0] == 'Ubuntu':
            node['cpu']['grubcmdline'] = 'GRUB_CMDLINE_LINUX_DEFAULT'
        else:
            node['cpu']['grubcmdline'] = 'GRUB_CMDLINE_LINUX'

        self._node = node
        self._current_cmdline = ""
        self._default_cmdline = ""
        self._get_current_cmdline()
        self._get_default_cmdline()
