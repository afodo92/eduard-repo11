#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# Created By  : Cosmin-Florin Stanuica, Alin Andronache
# Created Date: 01.2022
# version ='1.0'
# ---------------------------------------------------------------------------
""" Script used to deploy a runlist execution in Velocity based on Zephyr cycle information """
# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
import json
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import helpers.Logger as Local_logger
import libs.libs_velocity.Velocity as Velocity
from parameters.global_parameters import Reporting as REPORTINGPARAMS
from parameters.global_parameters import Jira as JIRAPARAMS
from parameters.global_parameters import Zephyr as ZEPHYRPARAMS
from parameters.global_parameters import Velocity as VELOCITYPARAMS


from datetime import datetime
from libs.libs_html_reporting.HTMLReportCore import HTMLGenerator
from libs.libs_jira.JiraCore import JiraCore
from libs.libs_zephyr.ZephyrCore import ZephyrCore

log_worker = Local_logger.create_logger(__name__, REPORTINGPARAMS["log_level_default"],
                                        REPORTINGPARAMS["test_log_path"], "s_run_zephyr_automation_cycle.txt")


def __jira_get_project_id(session, project_key):
    j_project_details = session.get_project_details(project_key=project_key)
    if not j_project_details:
        log_worker.error("Failed to get Jira Project details")
        return 0
    else:
        if "id" not in j_project_details.keys() or "versions" not in j_project_details.keys():
            log_worker.error("Failed to identify Jira Project ID or Version")
            return 0
    log_worker.info(f"Identified Jira Project ID for project {project_key}")
    return j_project_details["id"]


def __jira_get_project_version_id(session, project_key, jira_project_version_name):
    if jira_project_version_name.lower() == "unscheduled":
        log_worker.info(
            f"Identified Jira Project Version ID for project {project_key} with version name {jira_project_version_name}")
        return -1

    j_project_details = session.get_project_details(project_key=project_key)
    if "versions" not in j_project_details.keys():
        log_worker.error("Failed to get Jira Project Version")
        return 0
    for version in j_project_details["versions"]:
        if "name" not in version.keys() or "id" not in version.keys():
            continue
        if version["name"] == jira_project_version_name:
            log_worker.info(
                f"Identified Jira Project Version ID for project {project_key} with version name {jira_project_version_name}")
            return version["id"]
    return 0


def __zephyr_get_cycle_id(session, project_id, project_version, cycle_name):
    z_cycles_details = session.get_cycles(project_id=project_id, project_version=project_version)
    if not z_cycles_details:
        log_worker.error("Failed to get Zephyr Test Cycles details")
        return 0
    else:
        for current_cycle_id in z_cycles_details.keys():
            if isinstance(z_cycles_details[current_cycle_id], dict):
                if "name" not in z_cycles_details[current_cycle_id].keys():
                    continue
                if z_cycles_details[current_cycle_id]["name"] == cycle_name:
                    log_worker.info(f"Identified Zephyr Test Tycle ID for cycle {cycle_name}")
                    return current_cycle_id
            else:
                continue
    return 0


def __zephyr_get_all_cycle_test_keys(session, project_id, project_version, cycle_id):
    def get_folder_ids(z_folders_details):
        folder_ids = []

        if z_folders_details and len(z_folders_details):
            for folder in z_folders_details:
                if "folderId" not in folder:
                    continue
                log_worker.debug(f"Identified Zephyr folder {folder['folderId']}")
                folder_ids.append(folder["folderId"])

        return folder_ids

    def get_executions_test_keys(z_executions):
        executions_test_keys = []
        if "executions" in z_executions.keys():
            for execution in z_executions["executions"]:
                if "issueKey" not in execution.keys():
                    continue
                log_worker.debug(f"Identified Zephyr execution {execution['issueKey']}")
                executions_test_keys.append(execution["issueKey"])

        return executions_test_keys

    test_keys_list = []

    ''' Get Zephyr Folders included in the Test Cycle '''
    z_folders_details = session.get_cycle_folders_information_by_id(project_id=project_id,
                                                                    project_version=project_version, cycle_id=cycle_id)
    zephyr_folder_ids = get_folder_ids(z_folders_details)

    ''' Get Zephyr Executions included DIRECTLY in the Test Cycle '''
    z_executions = session.get_test_executions_by_zephyr_ids(project_id=project_id, project_version=project_version,
                                                             cycle_id=cycle_id)
    if not z_executions:
        log_worker.error(f"Failed to get executions under Test Cycle with ID {cycle_id}")
    else:
        test_keys_list += get_executions_test_keys(z_executions)

    ''' Get Zephyr Executions included in the Test Cycle Folders '''
    for folder_id in zephyr_folder_ids:
        z_executions = session.get_test_executions_by_zephyr_ids(project_id=project_id, project_version=project_version,
                                                                 cycle_id=cycle_id, folder_id=folder_id)
        if not z_executions:
            log_worker.error(f"Failed to get executions under Test Cycle with ID {cycle_id} folder {folder_id}")
        else:
            test_keys_list += get_executions_test_keys(z_executions)

    return test_keys_list


def __zephyr_get_all_cycle_test_keys_with_execution_ids(session: ZephyrCore, project_id, project_version, cycle_id):
    def get_folder_ids(z_folders_details):
        folder_ids = []

        if z_folders_details and len(z_folders_details):
            for folder in z_folders_details:
                if "folderId" not in folder:
                    continue
                log_worker.debug(f"Identified Zephyr folder {folder['folderId']}")
                folder_ids.append(folder["folderId"])

        return folder_ids

    def get_executions_test_key_to_id_data(z_executions):
        executions_data = {}
        if "executions" in z_executions.keys():
            for execution in z_executions["executions"]:
                if "issueKey" not in execution.keys() or "id" not in execution.keys():
                    continue
                log_worker.debug(f"Identified Zephyr execution {execution['issueKey']} with ID {execution['id']}")
                executions_data[execution["issueKey"]] = execution["id"]

        return executions_data

    executions_complete_data = {}

    ''' Get Zephyr Folders included in the Test Cycle '''
    z_folders_details = session.get_cycle_folders_information_by_id(project_id=project_id,
                                                                    project_version=project_version, cycle_id=cycle_id)
    zephyr_folder_ids = get_folder_ids(z_folders_details)

    ''' Get Zephyr Executions included DIRECTLY in the Test Cycle '''
    z_executions = session.get_test_executions_by_zephyr_ids(project_id=project_id, project_version=project_version,
                                                             cycle_id=cycle_id)
    if not z_executions:
        log_worker.error(f"Failed to get executions under Test Cycle with ID {cycle_id}")
    else:
        executions_complete_data.update(get_executions_test_key_to_id_data(z_executions))

    ''' Get Zephyr Executions included in the Test Cycle Folders '''
    for folder_id in zephyr_folder_ids:
        z_executions = session.get_test_executions_by_zephyr_ids(project_id=project_id, project_version=project_version,
                                                                 cycle_id=cycle_id, folder_id=folder_id)
        if not z_executions:
            log_worker.error(f"Failed to get executions under Test Cycle with ID {cycle_id} folder {folder_id}")
        else:
            executions_complete_data.update(get_executions_test_key_to_id_data(z_executions))

    return executions_complete_data


def __zephyr_create_cycle(session: ZephyrCore, project_id, project_version, cycle_name, build, test_keys_to_include):
    z_cycle_information = session.create_cycle(name=cycle_name, project_id=project_id, project_version=project_version,
                                               build=build)

    if z_cycle_information:
        log_worker.info(f"Created Zephyr cycle {cycle_name}")
        test_cycle_id = z_cycle_information["id"]

        zephyr_job_information = session.add_tests_to_cycle_by_key_list(project_id=project_id,
                                                                        project_version=project_version,
                                                                        cycle_id=test_cycle_id,
                                                                        test_key_list=test_keys_to_include)
        if not zephyr_job_information or "jobProgressToken" not in zephyr_job_information.keys():
            log_worker.error("Failed to start job to add tests to the Test Cycle")
            return 0
        else:
            for time_slot in range(60):
                zephyr_job_details = session.get_job_progress_by_token(
                    job_progress_token=zephyr_job_information["jobProgressToken"])
                if not zephyr_job_details or "progress" not in zephyr_job_details.keys():
                    log_worker.error("Failed to get progress from add tests to Test Cycle job ")
                else:
                    if zephyr_job_details["progress"] == 1:
                        log_worker.info(f"Added Tests to Zephyr cycle {cycle_name}")
                        return test_cycle_id
                time.sleep(2)
            log_worker.error("Failed to complete job to add tests to the Test Cycle - Max timer expired")
            return 0
    else:
        log_worker.error(f"Failed to create Zephyr cycle {cycle_name}")
        return 0


def __zephyr_update_test_executions(session: ZephyrCore, update_data):
    update_pass = []
    update_fail = []

    for test_key, test_data in update_data.items():
        if test_data["result"] is not None and test_data["execution_id"] is not None:
            z_execution_update_information = session.update_test_execution_status_by_id(
                execution_id=test_data["execution_id"], execution_status=test_data["result"])
            if z_execution_update_information:
                log_worker.info(
                    f"Updated Zephyr Execution with ID {test_data['execution_id']} and result {test_data['result']}")
                update_pass.append(test_key)
            else:
                log_worker.warning(
                    f"Failed to Update Zephyr Execution with ID {test_data['execution_id']} and result {test_data['result']}")
                update_fail.append(test_key)

    return {"update_pass": update_pass, "update_fail": update_fail}


def __build_update_data(automation_results_data, execution_key_id_data):
    update_data_structure = {}
    for test_key in set(list(automation_results_data.keys()) + list(execution_key_id_data.keys())):
        update_data_structure[test_key] = {}
        if test_key in automation_results_data.keys():
            update_data_structure[test_key] = automation_results_data[test_key]
        else:
            update_data_structure[test_key]["test_name"] = None
            update_data_structure[test_key]["result"] = None
            update_data_structure[test_key]["execution_link"] = ""
            update_data_structure[test_key]["failure_reason"] = ""

        if test_key in execution_key_id_data.keys():
            update_data_structure[test_key]["execution_id"] = execution_key_id_data.get(test_key)
        else:
            update_data_structure[test_key]["execution_id"] = None

    return (update_data_structure)


def __build_pass_fail_summary(update_data):
    pass_count = 0
    fail_count = 0
    indeterminate_count = 0
    for test_key, test_data in update_data.items():
        if test_data["result"] is not None and test_data["result"].lower() == "pass":
            pass_count += 1
            continue
        if test_data["result"] is not None and test_data["result"].lower() == "fail":
            fail_count += 1
            continue
        indeterminate_count += 1

    return {"pass": pass_count, "fail": fail_count, "indeterminate": indeterminate_count,
            "total": pass_count + fail_count + indeterminate_count}


def __build_html_report(session: HTMLGenerator, output_file, test_cycle, build, runlist_link, time_date,
                        pass_fail_summary, results_data, not_run_list):
    html_generation_result = session.airtel_report_generator(output_file=output_file,
                                                             test_cycle=test_cycle, build=build,
                                                             runlist_link=runlist_link,
                                                             time_date=time_date, pass_fail_summary=pass_fail_summary,
                                                             results_data=results_data,
                                                             not_run_list=not_run_list)
    if html_generation_result:
        log_worker.info(f"Generated HTML Automation report under {output_file}")
        return True
    else:
        log_worker.error(f"Failed to generate HTML Automation report under {output_file}")
        return False


def __jira_add_comment(session: JiraCore, story_key, project_key, project_version_name, cycle_name, runlist_link,
                       pass_fail_summary, update_pass_list=[], update_fail_list=[], update_not_run_list=[],
                       attachment_location=None):
    test_count_pass = pass_fail_summary["pass"]
    test_count_fail = pass_fail_summary["fail"]
    test_count_indeterminate = pass_fail_summary["indeterminate"]
    test_count_total = pass_fail_summary["total"]
    test_count_not_run = pass_fail_summary["not_run"]

    comment = f"Test Execution results were added to Jira project: {project_key}, version: {project_version_name} in Zephyr Test Cycle: {cycle_name}\n"
    comment += f"RunList details available here: {runlist_link}\n"
    comment += f"PASS PERCENTAGE: {str(round(float(100 * test_count_pass / (test_count_total - test_count_not_run)), 2))}% ({test_count_pass} pass, {test_count_fail} fail, {test_count_indeterminate} indeterminate)\n"

    if attachment_location:
        if not session.attach_file(item_key=story_key, file_path=attachment_location):
            log_worker.error(f"Failed to attach {attachment_location} file to Jira story {story_key}")
        else:
            log_worker.info(f"Attached {attachment_location} file to Jira story {story_key}")
            comment += f"Automation Report: [^{os.path.split(attachment_location)[1]}]\n"

    comment += "\n"
    comment += "Zephyr executions update status:\n"
    comment += f"- Executions for which the result was logged successfully in Zephyr: {', '.join(update_pass_list)}\n"
    comment += f"- Executions for which the result was NOT logged successfully in Zephyr: {', '.join(update_fail_list)}\n"
    comment += f"- Skipped executions: {', '.join(update_not_run_list)}"

    return session.add_comment(item_key=story_key, content=comment)


def zephyr_get_test_keys_from_cycle(jira_project_key, jira_project_version_name, zephyr_test_cycle_name,
                                    velocity_session):
    ''' Initialize variables'''
    jira_project_id = 0
    jira_project_version_id = 0
    zephyr_cycle_id = 0
    test_keys_list = []
    return_data = {"ok": False, "test_cycle_id": 0, "test_keys_list": []}

    jira_service_name = JIRAPARAMS['service_name_velo']
    properties_list = ['ipAddress', 'username', 'password']
    jira_host = velocity_session.get_resource_property_value(jira_service_name, properties_list)

    zephyr_service_name = ZEPHYRPARAMS['service_name_velo']
    properties_list = ['ipAddress', 'username', 'password']
    zephyr_host = velocity_session.get_resource_property_value(zephyr_service_name, properties_list)

    ''' Open Sessions '''
    log_worker.info(
        f'Opening Jira session on {jira_host["ipAddress"]} with user {jira_host["username"]}')
    jira = JiraCore(jira_host["ipAddress"], jira_host["username"], jira_host["password"])
    log_worker.info(
        f'Opening Zephyr session on {zephyr_host["ipAddress"]} with user {zephyr_host["username"]}')
    zephyr = ZephyrCore(zephyr_host["ipAddress"], zephyr_host["username"], zephyr_host["password"])
    if not zephyr.login():
        log_worker.error("Failed to open sessions")
        return return_data

    ''' Get Jira Project ID and Version - needed for Zephyr actions '''
    jira_project_id = __jira_get_project_id(session=jira, project_key=jira_project_key)
    jira_project_version_id = __jira_get_project_version_id(session=jira, project_key=jira_project_key,
                                                            jira_project_version_name=jira_project_version_name)
    if jira_project_id == 0 or jira_project_version_id == 0:
        log_worker.error(
            f"Failed to identify IDs for project {jira_project_key} with Version name {jira_project_version_name}")
        return return_data

    ''' Get Zephyr Cycle ID '''
    zephyr_cycle_id = __zephyr_get_cycle_id(session=zephyr, project_id=jira_project_id,
                                            project_version=jira_project_version_id, cycle_name=zephyr_test_cycle_name)
    if zephyr_cycle_id == 0:
        log_worker.error(f"Failed to identify ID for Test Cycle {zephyr_test_cycle_name}")
        return return_data

    ''' Get Test Keys included in the Zephyr Test Cycle '''
    return_data["ok"] = True
    return_data["test_cycle_id"] = zephyr_cycle_id
    return_data["test_keys_list"] = __zephyr_get_all_cycle_test_keys(session=zephyr, project_id=jira_project_id,
                                                                     project_version=jira_project_version_id,
                                                                     cycle_id=zephyr_cycle_id)

    ''' Return the data'''
    return return_data


def zephyr_init_session_automation_results(automation_test_keys_list, jira_project_key, jira_project_version_name,
                                           zephyr_create_cycle_flag, zephyr_test_cycle_name, zephyr_build, zephyr_host, jira_host):
    ''' Initialize variables '''

    jira_project_id = 0
    jira_project_version_id = 0
    zephyr_cycle_id = 0
    execution_key_id_data = {}

    ''' Open Sessions '''
    try:
        log_worker.info(
            f'Opening Jira session on {jira_host["ipAddress"]} with user {jira_host["username"]}')
        jira = JiraCore(jira_host["ipAddress"], jira_host["username"], jira_host["password"])
    except Exception as e:
        log_worker.error(f"Failed to open JIRA sessions\n {e}")
        return {"ok": False}

    log_worker.info(
        f'Opening Zephyr session on {zephyr_host["ipAddress"]} with user {zephyr_host["username"]}')
    zephyr = ZephyrCore(zephyr_host["ipAddress"], zephyr_host["username"], zephyr_host["password"])
    if not zephyr.login():
        log_worker.error("Failed to open Zephyr sessions")
        return {"ok": False}

    ''' Get Jira Project ID and Version - needed for Zephyr actions '''
    jira_project_id = __jira_get_project_id(session=jira, project_key=jira_project_key)
    jira_project_version_id = __jira_get_project_version_id(session=jira, project_key=jira_project_key,
                                                            jira_project_version_name=jira_project_version_name)
    if jira_project_id == 0 or jira_project_version_id == 0:
        log_worker.error(
            f"Failed to identify IDs for project {jira_project_key} with Version name {jira_project_version_name}")
        return {"ok": False}

    ''' Create Zephyr Test Cycle if needed '''
    if zephyr_create_cycle_flag:
        zephyr_cycle_id = __zephyr_create_cycle(session=zephyr, project_id=jira_project_id,
                                                project_version=jira_project_version_id,
                                                cycle_name=zephyr_test_cycle_name, build=zephyr_build,
                                                test_keys_to_include=automation_test_keys_list)
    else:
        zephyr_cycle_id = __zephyr_get_cycle_id(session=zephyr, project_id=jira_project_id,
                                                project_version=jira_project_version_id,
                                                cycle_name=zephyr_test_cycle_name)
    if zephyr_cycle_id == 0:
        log_worker.error(f"Failed to identify ID for Test Cycle {zephyr_test_cycle_name}")
        return {"ok": False}
    #
    ''' Get Zephyr Test Cycle Executions - map IDs to Test Keys '''
    execution_key_id_data = __zephyr_get_all_cycle_test_keys_with_execution_ids(session=zephyr,
                                                                                project_id=jira_project_id,
                                                                                project_version=jira_project_version_id,
                                                                                cycle_id=zephyr_cycle_id)
    if not execution_key_id_data:
        log_worker.error("Failed to map execution Keys to IDs")
        return {"ok": False}

    return {"ok": True, "zephyr_session": zephyr, "jira_session": jira, "execution_key_id_data": execution_key_id_data}


def zephyr_update_test_executions(zephyr, automation_results_data, execution_key_id_data):
    ''' Build Update data by joining automation results to the execution keys, as known by Zephyr'''
    update_data = __build_update_data(automation_results_data=automation_results_data,
                                      execution_key_id_data=execution_key_id_data)
    pass_fail_summary = __build_pass_fail_summary(update_data=update_data)

    ''' Upload execution details for each test to Zephyr Test Cycle '''
    update_result_information = __zephyr_update_test_executions(session=zephyr, update_data=update_data)
    update_pass_list = update_result_information["update_pass"]
    update_fail_list = update_result_information["update_fail"]
    if not update_pass_list and not update_fail_list:
        log_worker.error("Failed to attempt Zephyr Test results update - No successful or failure update")
        return {"ok": False}

    return {"ok": True, "update_pass_list": update_pass_list, "update_fail_list": update_fail_list,
            "update_data": update_data, "pass_fail_summary": pass_fail_summary}


def generate_html_report(zephyr_test_cycle_name, zephyr_build, pass_fail_summary, update_data, runlist_link,
                         jira, jira_project_key, jira_project_version_name, story_key_for_comment, update_pass_list,
                         update_fail_list, update_not_run_list):
    try:
        html_generator = HTMLGenerator("airtel_automation_report.html")
    except Exception as e:
        log_worker.error(f"Failed to open HTML Generator sessions\n {e}")
        return {"ok": False}

    current_time = datetime.now().strftime("%d-%m-%Y_%Hh%Mm%Ss")

    html_report_file = os.path.join(REPORTINGPARAMS["report_path"],
                                    f"auto_report_{zephyr_test_cycle_name}_{zephyr_build}_{current_time}.html")
    ''' Generate HTML Report '''
    if not __build_html_report(session=html_generator, output_file=html_report_file,
                               test_cycle=zephyr_test_cycle_name, build=zephyr_build, runlist_link=runlist_link,
                               time_date=current_time, pass_fail_summary=pass_fail_summary, results_data=update_data,
                               not_run_list=update_not_run_list):
        log_worker.error(f"Failed to Generate HTML report in file {html_report_file}")
        html_report_file = None

    ''' Add comment in Jira '''
    if story_key_for_comment:
        comment_result = __jira_add_comment(session=jira, story_key=story_key_for_comment, project_key=jira_project_key,
                                            project_version_name=jira_project_version_name,
                                            cycle_name=zephyr_test_cycle_name,
                                            runlist_link=runlist_link, pass_fail_summary=pass_fail_summary,
                                            update_pass_list=update_pass_list, update_fail_list=update_fail_list,
                                            update_not_run_list=update_not_run_list,
                                            attachment_location=html_report_file)
        if not comment_result:
            log_worker.error(f"Failed to add comment in Jira story {story_key_for_comment}")
            return {"ok": False}

    return {"ok": True}


def deploy_runlist_execution(cycle_id, keys_list, runlist_name, jira_project_version_name, jira_project_key,
                             zephyr_test_cycle_name, zephyr_build, velocity_session, topology_id, story_key_for_comment):
    velocity = VELOCITYPARAMS['host']
    jira_service_name = JIRAPARAMS['service_name_velo']
    properties_list = ['ipAddress', 'username', 'password']
    jira_host = velocity_session.get_resource_property_value(jira_service_name, properties_list)

    automation_results_data = {}
    testcases_list = []

    if runlist_name == "N/A":

        '''Get all matching scripts by list of tags'''
        zephyr_create_cycle_flag = 0
        to_exclude = []
        execution_name = cycle_id
        for tag in keys_list:

            filter_set = {"tags": [tag]}
            automation_assets = velocity_session.get_automation_assets(filters=filter_set)
            if len(automation_assets["content"]) != 0:

                log_worker.debug(f"Found {len(automation_assets['content'])} automation assets mathing tag {tag}")

                automation_results_data[tag] = {}
                automation_results_data[tag]["test_name"] = automation_assets["content"][0]["name"]
                log_worker.info(f"Testcase {automation_assets['content'][0]['name']} was found for tag: {tag}")
                testcases_list.append(automation_assets["content"][0]["fullPath"])

            else:
                log_worker.warning(f"No testcases were found for tag: {tag}")
                to_exclude.append(tag)

        log_worker.warning(f"Testcases for tags {to_exclude} were not found and will be ignored.")
        for tag in to_exclude:
            keys_list.remove(tag)

        if len(automation_results_data.keys()) == 0:
            log_worker.warning(f"No testcases were found for tags {keys_list}, exiting execution.")
            sys.exit(0)

    else:
        log_worker.info(f"Getting the list of runlist test cases for {runlist_name}")
        zephyr_create_cycle_flag = 1
        zephyr_test_cycle_name = runlist_name + "_" + datetime.now().strftime("%d-%m-%Y_%Hh%Mm%Ss")
        keys_list = []
        execution_name = runlist_name

        runlist_info = velocity_session.get_runlist(runlist_name=runlist_name)
        log_worker.debug(f"Runlist info: {runlist_info}")

        topology_id = runlist_info["general"]["topologyId"]
        for i in range(0, len(runlist_info["main"]["items"])):
            full_path = runlist_info["main"]["items"][i]["path"]
            log_worker.info(f"Testcase full path: {full_path}")
            filter_set = {"fullPath": full_path}
            automation_asset_info = velocity_session.get_automation_assets(filters=filter_set)

            if len(automation_asset_info["content"]) == 1:
                log_worker.debug(f"Following testcases were found while using filter: {filter_set}: "
                                 f"{automation_asset_info}")
                tag = automation_asset_info["content"][0]["tags"][0]
                automation_results_data[tag] = {}
                automation_results_data[tag]["test_name"] = automation_asset_info["content"][0]["name"]
                testcases_list.append(full_path)
                log_worker.debug(f"Current list of testcases: {testcases_list}")
                keys_list.append(tag)
                log_worker.debug(f"Current list of keys: {keys_list}")

            else:
                log_worker.error(f"No testcases were found while using filter: {filter_set}. Request response: "
                                 f"{automation_asset_info}")

    '''Start Jira - Zephyr execution update sessions and get existing execution key ID data'''

    init_session_result = zephyr_init_session_automation_results(automation_test_keys_list=keys_list,
                                                                 jira_project_key=jira_project_key,
                                                                 jira_project_version_name=jira_project_version_name,
                                                                 zephyr_create_cycle_flag=zephyr_create_cycle_flag,
                                                                 zephyr_test_cycle_name=zephyr_test_cycle_name,
                                                                 zephyr_build=zephyr_build,
                                                                 zephyr_host=jira_host, jira_host=jira_host)

    if init_session_result["ok"]:
        zephyr = init_session_result["zephyr_session"]
        jira = init_session_result["jira_session"]
        execution_key_id_data = init_session_result["execution_key_id_data"]
    else:
        return {"ok": False}

    '''Post runlist execution'''
    log_worker.info(f"Creating runlist execution using testcase list: {testcases_list}")

    runlist_execution_id = velocity_session.post_runlist_execution(testcase_paths=testcases_list,
                                                                   detail_level="ALL_ISSUES_ALL_STEPS",
                                                                   terminate_on_item_fail=False,
                                                                   execution_name=execution_name,
                                                                   topology_id=topology_id)

    if runlist_execution_id:
        log_worker.info(f"Runlist execution ID is: {runlist_execution_id}")
    else:
        log_worker.error("Failed to create runlist execution, exiting script execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

    '''Monitor runlist execution'''

    execution_status = {}
    temp_update_pass_list = []
    temp_update_fail_list = []
    temp_update_data = {}

    not_processed = testcases_list
    while not_processed:
        log_worker.info(f"Entering runlist monitoring cycle for: {runlist_execution_id}")
        processed = []
        temp_results = {}
        execution_status = velocity_session.get_runlist_execution(runlist_execution_id)[0]
        log_worker.debug(f"Current execution status: {execution_status}")
        log_worker.debug(f"Executions not processed: {not_processed}")

        if len(execution_status["executions"]) > 0:
            for testcase in not_processed:
                test_index = -1
                try:
                    test_index = [i for i in range(0, len(execution_status["executions"])) if
                                  testcase == execution_status["executions"][i]["testPath"]][0]
                except Exception as e:
                    if e == "list index out of range":
                        pass
                if test_index != '':
                    if execution_status["executions"][test_index]["executionState"] in ["COMPLETED", "START_FAILED",
                                                                                        "ABORTED",
                                                                                        "AGENT_NOT_RESPONDING"]:

                        for tag in automation_results_data.keys():
                            if automation_results_data[tag]["test_name"] in testcase:
                                break
                        temp_results[tag] = {}
                        temp_results[tag]["test_name"] = automation_results_data[tag]["test_name"]
                        temp_testcase_result = execution_status["executions"][test_index]["result"]
                        testcase_execution_id = execution_status['executions'][test_index]['executionID']

                        '''Added logic to retry 3 times in case execution state returns INDETERMINATE value'''

                        retries = 1
                        while temp_testcase_result == "INDETERMINATE" and retries < 11:
                            log_worker.warning(f"Testcase {testcase_execution_id} has executionState COMPLETED but "
                                               f"results INDETERMINATE. Retry: {retries}.")
                            time.sleep(10)
                            testcase_execution_status = velocity_session.get_execution_id(execution_id=testcase_execution_id)
                            if type(testcase_execution_status) is not dict:
                                testcase_execution_status = json.loads(testcase_execution_status)
                            temp_testcase_result = testcase_execution_status["result"]
                            retries += 1
                        temp_results[tag]["result"] = temp_testcase_result
                        log_worker.info(f"Execution of {automation_results_data[tag]['test_name']} is completed."
                                        f"with execution ID {testcase_execution_id} and result "
                                        f"{temp_results[tag]['result']}")

                        temp_results[tag][
                            "execution_link"] = f"https://{velocity}/velocity/reports/executions/{testcase_execution_id}"
                        execution_id_response = velocity_session.get_execution_id(testcase_execution_id)
                        failure_reason = execution_id_response["failureReason"]
                        if failure_reason is None:
                            failure_reason = velocity_session.get_execution_failure_reason(testcase_execution_id)
                            temp_results[tag]["failure_reason"] = failure_reason
                        else:
                            temp_results[tag]["failure_reason"] = failure_reason
                        processed.append(testcase)
                        if failure_reason:
                            log_worker.info(f"Execution of {automation_results_data[tag]['test_name']} failed, opening "
                                            f"Jira issue.")
                            failure_reason = failure_reason.replace('"', '')
                            open_defect = jira.open_defect(jira_project_key, summary=f"{temp_results[tag]['test_name']}"
                                                                                     f" has failed.",
                                                           description="Link to the Velocity execution report: " + temp_results[tag]["execution_link"])
                            if open_defect is not False:
                                log_worker.info(f"Jira issue {open_defect} has been opened.")
                                link_result = jira.link_item(open_defect, story_key_for_comment, "relates")
                                if link_result is not False:
                                    log_worker.info(
                                        f"Jira issue {open_defect} has been linked to {story_key_for_comment}.")
                                else:
                                    log_worker.error(
                                        f"Failed to link Jira issue {open_defect} to {story_key_for_comment}.")
                            else:
                                log_worker.error(f"Failed to open Jira issue.")

                        not_processed.remove(testcase)

        if temp_results != {}:
            log_worker.debug(f"Current temp results: {temp_results}")

            upload_partial_results = zephyr_update_test_executions(zephyr=zephyr,
                                                                   automation_results_data=temp_results,
                                                                   execution_key_id_data=execution_key_id_data)
            log_worker.debug(f"Partial results from latest scan: {upload_partial_results}")
            if upload_partial_results["ok"]:
                temp_update_pass_list.extend(upload_partial_results["update_pass_list"])
                log_worker.debug(f"Complete results until now -- temp_update_pass_list -- {temp_update_pass_list}")
                temp_update_fail_list.extend(upload_partial_results["update_fail_list"])
                log_worker.debug(f"Complete results until now -- temp_update_fail_list -- {temp_update_fail_list}")
                if temp_update_data == {}:
                    temp_update_data = upload_partial_results
                else:
                    for tag in upload_partial_results["update_data"].keys():
                        if upload_partial_results["update_data"][tag]["test_name"] is not None:
                            temp_update_data["update_pass_list"].extend(upload_partial_results["update_pass_list"])
                            temp_update_data["update_fail_list"].extend(upload_partial_results["update_fail_list"])
                            temp_update_data["update_data"][tag]["test_name"] = \
                                upload_partial_results["update_data"][tag]["test_name"]
                            temp_update_data["update_data"][tag]["result"] = upload_partial_results["update_data"][tag][
                                "result"]
                            temp_update_data["update_data"][tag]["execution_link"] = \
                                upload_partial_results["update_data"][tag][
                                    "execution_link"]
                            temp_update_data["update_data"][tag]["failure_reason"] = \
                                upload_partial_results["update_data"][tag][
                                    "failure_reason"]
                            temp_update_data["update_data"][tag]["execution_id"] = \
                                upload_partial_results["update_data"][tag][
                                    "execution_id"]
                log_worker.debug(f"Complete results until now -- temp_update_data -- {temp_update_data}")


            else:
                return {"ok": False}

        else:
            interval = 20
            log_worker.info(f"Runlist monitoring cycle info: no executions are finished yet, waiting for {interval} seconds.")
            time.sleep(interval)

    runlist_link = f"https://{velocity}/velocity/reports/runlists/{execution_status['guid']}"
    log_worker.info(f"Runlist execution is finished.")

    temp_update_data["pass_fail_summary"]["pass"] = len(
        [i for i in temp_update_data["update_data"].keys() if temp_update_data["update_data"][i]["result"] == "PASS"])
    temp_update_data["pass_fail_summary"]["fail"] = len(
        [i for i in temp_update_data["update_data"].keys() if temp_update_data["update_data"][i]["result"] == "FAIL"])
    temp_update_data["pass_fail_summary"]["total"] = len(temp_update_data["update_data"].keys())
    # temp_update_data["pass_fail_summary"]["indeterminate"] = temp_update_data["pass_fail_summary"]["total"] - (
    #         temp_update_data["pass_fail_summary"]["pass"] + temp_update_data["pass_fail_summary"]["fail"])
    temp_update_data["pass_fail_summary"]["indeterminate"] = len(
        [i for i in temp_update_data["update_data"].keys() if temp_update_data["update_data"][i]["result"] == "INDETERMINATE"])

    did_not_run = [tag for tag in temp_update_data["update_data"].keys() if
                   temp_update_data["update_data"][tag]["result"] is None]

    for tag in did_not_run:
        temp_update_data["update_data"].pop(tag)

    pass_fail_summary = {"pass": temp_update_data["pass_fail_summary"]["pass"],
                         "fail": temp_update_data["pass_fail_summary"]["fail"],
                         "indeterminate": temp_update_data["pass_fail_summary"]["indeterminate"],
                         "not_run": len(did_not_run),
                         "total": temp_update_data["pass_fail_summary"]["total"]}

    log_worker.debug(f"Final update_data -- {temp_update_data}")
    log_worker.debug(f"Final pass_fail_summary -- {pass_fail_summary}")
    log_worker.debug(f"Final update_pass_list -- {temp_update_pass_list}")
    log_worker.debug(f"Final update_fail_list -- {temp_update_fail_list}")
    log_worker.debug(f"SUCCESS")
    # jira = "test"
    return {"ok": True, "pass_fail_summary": pass_fail_summary, "update_pass_list": temp_update_pass_list,
            "update_fail_list": temp_update_fail_list, "update_data": temp_update_data["update_data"],
            "runlist_link": runlist_link, "jira_session": jira, "not_run": did_not_run}


def main():
    """Main procedure"""

    '''Initializing arguments'''
    jira_project_key = ""
    jira_project_release_name = ""
    zephyr_test_cycle_name = ""
    story_key_for_comment = ""
    zephyr_build = ""
    runlist_name = ""
    topology_name = ""

    for i in range(1, len(sys.argv[1:]), 2):
        log_worker.info(f"Argument: {sys.argv[i]}")
        log_worker.info(f"Value: {sys.argv[i + 1]}")
        if sys.argv[i] == "--jira_project_key":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            jira_project_key = sys.argv[i + 1]
        elif sys.argv[i] == "--jira_project_release_name":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            jira_project_release_name = sys.argv[i + 1]
        elif sys.argv[i] == "--zephyr_test_cycle_name":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            zephyr_test_cycle_name = sys.argv[i + 1]
        elif sys.argv[i] == "--keys_list":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            zephyr_build = sys.argv[i + 1]
        elif sys.argv[i] == "--story_key_for_comment":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            story_key_for_comment = sys.argv[i + 1]
        elif sys.argv[i] == "--zephyr_build":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            zephyr_build = sys.argv[i + 1]
        elif sys.argv[i] == "--runlist_name":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            runlist_name = sys.argv[i + 1]
        elif sys.argv[i] == "--topology_name":
            log_worker.info(f"Value for {sys.argv[i]} is {sys.argv[i + 1]}.")
            topology_name = sys.argv[i + 1]
        else:
            log_worker.warning(f"Argument {sys.argv[i]} is not recognized and will not be used.")

    if jira_project_key == "":
        log_worker.error(f"Argument jira_project_key is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if jira_project_release_name == "":
        log_worker.error(f"Argument jira_project_release_name is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if zephyr_test_cycle_name == "":
        log_worker.error(f"Argument zephyr_test_cycle_name is empty, exiting execution. Set as N/A if runlist_name is "
                         f"provided.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if story_key_for_comment == "":
        log_worker.error(f"Argument story_key_for_comment is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if zephyr_build == "":
        log_worker.error(f"Argument zephyr_build is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if runlist_name == "":
        log_worker.error(f"Argument runlist_name is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)
    if topology_name == "":
        log_worker.error(f"Argument topology_name is empty, exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

    velocity = VELOCITYPARAMS['host']
    velo_user = VELOCITYPARAMS['user']
    velo_password = VELOCITYPARAMS['pass']
    '''Open Velocity Session'''
    velocity_session = Velocity.API(velocity, velo_user, velo_password)

    '''Retrieve the topology ID'''
    if topology_name != "N/A":
        topology_id = velocity_session.get_topology_id_by_name(topology_name)
    else:
        topology_id = ""

    '''Retrieve the keys for the specified cycle name'''

    if runlist_name == "N/A":
        test_keys = zephyr_get_test_keys_from_cycle(jira_project_key=jira_project_key,
                                                    jira_project_version_name=jira_project_release_name,
                                                    zephyr_test_cycle_name=zephyr_test_cycle_name,
                                                    velocity_session=velocity_session)

    else:
        test_keys = {"ok": runlist_name, "test_cycle_id": None, "test_keys_list": None}

    if test_keys["ok"]:
        final_execution_results = deploy_runlist_execution(cycle_id=test_keys["test_cycle_id"],
                                                           keys_list=test_keys["test_keys_list"],
                                                           jira_project_key=jira_project_key,
                                                           jira_project_version_name=jira_project_release_name,
                                                           zephyr_test_cycle_name=zephyr_test_cycle_name,
                                                           zephyr_build=zephyr_build,
                                                           runlist_name=runlist_name,
                                                           velocity_session=velocity_session,
                                                           topology_id=topology_id,
                                                           story_key_for_comment=story_key_for_comment)

    else:
        log_worker.error(f"Test keys could not be obtained. Response: {test_keys}."
                         f" Exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

    if final_execution_results["ok"]:

        generated_report = generate_html_report(zephyr_test_cycle_name=zephyr_test_cycle_name,
                                                zephyr_build=zephyr_build,
                                                jira_project_key=jira_project_key,
                                                jira_project_version_name=jira_project_release_name,
                                                story_key_for_comment=story_key_for_comment,
                                                jira=final_execution_results["jira_session"],
                                                pass_fail_summary=final_execution_results["pass_fail_summary"],
                                                update_pass_list=final_execution_results["update_pass_list"],
                                                update_fail_list=final_execution_results["update_fail_list"],
                                                update_not_run_list=final_execution_results["not_run"],
                                                update_data=final_execution_results["update_data"],
                                                runlist_link=final_execution_results["runlist_link"])

        if generated_report["ok"]:
            log_worker.info(
                f"Final execution results do not have an expected result. Response: {final_execution_results}."
                f" Exiting execution.")
            log_worker.info(f"Finished: PASSED")
        else:
            log_worker.error(f"Failed to post HTML report.")
            log_worker.error(f"Finished: FAILED")

    else:
        log_worker.error(f"Final execution results do not have an expected result. Response: {final_execution_results}."
                         f" Exiting execution.")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)


if __name__ == "__main__":
    main()
