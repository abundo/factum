#!/usr/bin/env python3
"""
Get list of devices from Device-API
Write configuration file for icinga2
"""

# python standard modules
import os
import sys

if "/opt" not in sys.path:
    sys.path.insert(0, "/opt")
try:
    import ablib.utils as abutils
    from ablib.email1 import Email
    from ablib.icinga import Icinga
    from ablib.devices import Device_Mgr
except:
    print("Error: Cannot import ablib.* check PYTHONPATH")
    sys.exit(1)

try:
    # modules installed with pip
    import jinja2
    from orderedattrdict import AttrDict

    # modules, installed with pip, django
    import django

    # Setup django environment
    sys.path.append(os.getcwd())
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

    # Setup django
    django.setup()

    # Import ORM models 
    from base.models import Device, Tag, Parent, Interface, InterfaceTag, Cache
    import lib.base_common as common

except:
    abutils.send_traceback()    # Error in script, send traceback to developer


users = {}   # Key is email address

icinga = None


def create_conf_file(filename, message=""):
    """
    Create a new configuration file, with header
    """
    f = open(filename, "w")
    f.write("//\n")
    f.write("// Auto-generated. Note: do not edit this file, your changes will be overwritten/lost\n")
    if message:
        f.write("// %s\n" % message)
    f.write("//\n")
    f.write("\n")
    return f


def write_devices(devices, changed=False):
    """
    """
    print()
    print("----- Writing config:", config.icinga_sync.hosts_file.tmp, "-----")
    host_template = jinja2.Environment(
        loader=jinja2.BaseLoader()).from_string(config.icinga_sync.host_template
    )

    f = create_conf_file(config.icinga_sync.hosts_file.tmp, "%s hosts" % len(devices))

    # ----- write hosts -----
    for name, device in devices.items():
        if name in config.icinga_sync.ignore_devices:
            continue
        if not device.enabled:
            print("  Ignoring %s, device is not enabled" % device["name"])
            continue
        if not device.primary_ip4:
            print(f"  Ignoring device '{name}', no primary_ip4")
            continue
        p = AttrDict()
        p.options = []
        
        if device.parents:
            p.options.append("  vars.pe_parents = [")
            for parent in device.parents:
                p.options.append('    %s,' % icinga.quote(parent))
            p.options.append("  ]")

        alarm_destination = device.get("alarm_destination", None)
        if alarm_destination:
            p.options.append("  vars.pe_alarm_destination = [%s]" % icinga.quote(alarm_destination))
            if alarm_destination not in users:
                users[alarm_destination] = 1
        else:
            p.options.append(config.icinga_sync.default_notification)

        alarm_timeperiod = device.get("alarm_timeperiod", None)
        if alarm_timeperiod:
            p.options.append(f'  vars.pe_alarm_timeperiod = "{alarm_timeperiod}"')

        backup_oxidized = device.get("backup_oxidized", None)
        if backup_oxidized:
            p.options.append("  vars.pe_backup_oxidized = true")

        p.options = "\n".join(p.options)
        device.comments = icinga.quote(device.comments) # ugly

        data = host_template.render(device=device, p=p)
        f.write(data)

    # ----- Write dependencies -----
    f.write("\n")
    f.write("\n")
    f.write("// %s\n" % ("-"*76))
    f.write("\n")
    dependency_template = jinja2.Environment(
        loader=jinja2.BaseLoader()).from_string(config.icinga_sync.dependency_template
    )
    for name, device in devices.items():
        if name in config.icinga_sync.ignore_devices:
            continue
        if not device.enabled:
            continue
        if not device.parents:
            continue
        parents = device.get("parents", None)
        if not parents:
            continue
        for parent in parents:
            if parent not in devices:
                print(f"Warning: Unknown parent '{parent}' on device '{name}'")
                continue
            if devices[parent].enabled:
                p = AttrDict()
                p.depname = f"host-{parent}_host-{name}"
                p.parent = parent
                data = dependency_template.render(device=device, p=p)
                f.write(data)
                f.write("\n")
        f.write("\n")
    f.close()

    t = config.icinga_sync.hosts_file
    changed = abutils.install_conf_file(src=t.tmp, 
                                      dst=t.dst, 
                                      changed=changed)
    return changed


def write_users(changed=False):
    """
    Write all email destinations, as users
    """
    print("\nWriting config:", config.icinga_sync.users_file.tmp)
    f = create_conf_file(config.icinga_sync.users_file.tmp)
    for destination in users:
        d = AttrDict()
        d.username = destination
        d.displayname = destination
        d.email = destination
        f.write(config.icinga_sync.user_template.format_map(d))

    f.close()

    t = config.icinga_sync.users_file
    changed = abutils.install_conf_file(src=t.tmp,
                                      dst=t.dst, 
                                      changed=changed)
    return changed


def main():
    global icinga

    icinga = Icinga(config=config.icinga)

    print("----- Get devices from 'device-api' -----")
    device_mgr = Device_Mgr(config=config.device)
    tmp_devices = device_mgr.get_devices()

    print("----- Filter devices to monitor -----")
    devices = AttrDict()  # Key is name
    for name, device in tmp_devices.items():
        if not device.monitor_icinga:
            # print(f"  Ignoring '{name}', 'monitor_icinga' is False")
            continue
        devices[name] = device

    print("\n----- Write /etc/hosts entries -----")
    device_mgr.write_etc_hosts()

    changed = False   # Default, no changes => no reload
    changed = write_devices(devices, changed=changed)
    changed = write_users(changed=changed)
    
    if changed:
        print("\nAsking icinga to reload configuration")
        icinga.reload()
    else:
        print("\nNo change in icinga configuration")


if __name__ == "__main__":
    try:
        main()
    except:
        abutils.send_traceback()    # Error in script, send traceback to developer