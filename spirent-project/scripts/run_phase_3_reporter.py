import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from parameters.global_parameters import Velocity as VELOCITYPARAMS
from parameters.global_parameters import Jira as JIRAPARAMS
from parameters.global_parameters import Zephyr as ZEPHYRPARAMS
from parameters.global_parameters import Reporting as REPORTINGPARAMS
from libs.libs_html_reporting.HTMLReportCore import HTMLGenerator
from libs.libs_jira.JiraCore import JiraCore
from libs.libs_zephyr.ZephyrCore import ZephyrCore
from datetime import datetime
import helpers.Logger as Local_logger
import libs.libs_velocity.Velocity as Velocity



log_worker = Local_logger.create_logger(__name__, REPORTINGPARAMS["log_level_default"],
                                        REPORTINGPARAMS["test_log_path"], "s_run_zephyr_automation_cycle.txt")


def __build_comment(project_key, project_version_name, cycle_name, runlist_link,
                    pass_fail_summary, update_pass_list=[], update_fail_list=[], update_not_run_list=[],
                    attachment_location=None):
    test_count_pass = pass_fail_summary["pass"]
    test_count_fail = pass_fail_summary["fail"]
    test_count_indeterminate = pass_fail_summary["indeterminate"]
    test_count_total = pass_fail_summary["total"]
    test_count_not_run = pass_fail_summary["not_run"]

    comment = f"Test Execution results were added to Jira project: {project_key}, version: {project_version_name} in Zephyr Test Cycle: {cycle_name}\n"
    comment += f"RunList details available here:  {runlist_link}\n"
    comment += f"PASS PERCENTAGE: {str(round(float(100 * test_count_pass / (test_count_total - test_count_not_run)), 2))}% ({test_count_pass} pass, {test_count_fail} fail, {test_count_indeterminate} indeterminate)\n"
    if attachment_location:
        comment += f"Automation Report: [^{os.path.split(attachment_location)[1]}]\n"
    comment += "\n"
    comment += "Zephyr executions update status:\n"
    comment += f"- Executions for which the result was logged successfully in Zephyr: {', '.join(update_pass_list)}\n"
    comment += f"- Executions for which the result was NOT logged successfully in Zephyr: {', '.join(update_fail_list)}\n"
    comment += f"- Skipped executions: {', '.join(update_not_run_list)}"

    return comment


def __extract_runlist_details(runlist_data, test_key_script_mapping, velocity_session):
    tests_not_executed_list = []
    tests_passed_list = []
    tests_failed_list = []
    tests_indeterminate_list = []
    results_data = {}
    pass_fail_summary = {}

    runlist_data = runlist_data[0]
    test_executions = []
    for execution in runlist_data.get("executions"):
        full_path = execution.get("testPath")
        filter_set = {"fullPath": full_path}
        automation_assets = velocity_session.get_automation_assets(filters=filter_set)
        if len(automation_assets["content"]) > 0 and automation_assets["content"][0]["tags"] and "airtel_monitor" not in automation_assets["content"][0]["tags"] and "airtel_reporter" not in automation_assets["content"][0]["tags"]:
            test_executions.append(execution)

    for execution in test_executions:
        test_name = execution.get("testPath").split("/")[-1]
        test_result = execution.get("result")
        test_execution_link = f"https://{velocity}/velocity/reports/executions/{execution.get('executionID')}"

        execution_details = velocity_session.get_execution_id(execution.get("executionID"))
        if execution_details.get("failureReason"):
            failure_reason = execution_details.get("failureReason")
        else:
            failure_reason = velocity_session.get_execution_failure_reason(execution.get("executionID"))

        for test_key in test_key_script_mapping.keys():
            if test_key_script_mapping[test_key] == test_name:
                break

        if test_result is None or test_result.lower() in ["start_failed", "aborted", "agent_not_responding"]:
            tests_not_executed_list.append(test_key)
        if test_result.lower() == "pass":
            tests_passed_list.append(test_key)
        if test_result.lower() == "fail":
            tests_failed_list.append(test_key)
        if test_result.lower() == "indeterminate":
            tests_indeterminate_list.append(test_key)

        results_data[test_key] = {"test_name": test_name, "result": test_result, "failure_reason": failure_reason, "execution_link": test_execution_link}

    pass_fail_summary["pass"] = len(tests_passed_list)
    pass_fail_summary["fail"] = len(tests_failed_list)
    pass_fail_summary["indeterminate"] = len(tests_indeterminate_list)
    pass_fail_summary["not_run"] = len(tests_not_executed_list)
    pass_fail_summary["total"] = len(test_executions)

    return {"pass_fail_summary": pass_fail_summary, "results_data":results_data, "pass_list": tests_passed_list, "fail_list": tests_failed_list, "indeterminate_list": tests_indeterminate_list, "not_run_list":tests_not_executed_list}


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

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--jira_project_key', required=True, dest="JIRA_PROJECT_KEY")
parser.add_argument('--jira_project_release_name', required=True, dest="JIRA_PROJECT_RELEASE_NAME")
parser.add_argument('--zephyr_test_cycle_name', required=True, dest="ZEPHYR_TEST_CYCLE_NAME")
parser.add_argument('--story_key_for_comment', required=True, dest="STORY_KEY_FOR_COMMENT")
parser.add_argument('--zephyr_build', required=True, dest="ZEPHYR_BUILD")
parser.add_argument('--runlist_name', required=True, dest="RUNLIST_NAME")
parser.add_argument('--topology_name', required=True, dest="TOPOLOGY_NAME")
parser.add_argument('--zephyr_test_cycle_id', required=True, dest="ZEPHYR_TEST_CYCLE_ID")

jira_project_key = parser.parse_known_args()[0].JIRA_PROJECT_KEY
jira_project_release_name = parser.parse_known_args()[0].JIRA_PROJECT_RELEASE_NAME
zephyr_test_cycle_name = parser.parse_known_args()[0].ZEPHYR_TEST_CYCLE_NAME
story_key_for_comment = parser.parse_known_args()[0].STORY_KEY_FOR_COMMENT
zephyr_build = parser.parse_known_args()[0].ZEPHYR_BUILD
runlist_name = parser.parse_known_args()[0].RUNLIST_NAME
topology_name = parser.parse_known_args()[0].TOPOLOGY_NAME
zephyr_test_cycle_id = parser.parse_known_args()[0].ZEPHYR_TEST_CYCLE_ID



'''Local Variables'''
velocity = VELOCITYPARAMS['host']
velo_user = VELOCITYPARAMS['user']
velo_password = VELOCITYPARAMS['pass']



''' SESSION MANAGEMENT - Open Sessions '''
opening_sessions_failed = 0
log_worker.info(f'Opening Velocity session on {velocity} with user {velo_user}')
try:
    velocity_session = Velocity.API(velocity, velo_user, velo_password)
except Exception as e:
    log_worker.error(f"Failed to open Velocity session. Exiting Execution\n {e}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

jira_service_name = JIRAPARAMS['service_name_velo']
properties_list = ['ipAddress', 'username', 'password']
properties_jira = velocity_session.get_resource_property_value(jira_service_name, properties_list)
if not properties_jira:
    log_worker.error(f"Failed to identify resource in velocity for Jira Service Name {jira_service_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)
log_worker.info(f'Opening Jira session on {properties_jira["ipAddress"]} with user {properties_jira["username"]}')
try:
    jira = JiraCore(properties_jira["ipAddress"], properties_jira["username"], properties_jira["password"])
except Exception as e:
    log_worker.error(f"Failed to open Jira session. Exiting Execution\n {e}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

zephyr_service_name = ZEPHYRPARAMS['service_name_velo']
properties_list = ['ipAddress', 'username', 'password']
properties_zephyr = velocity_session.get_resource_property_value(zephyr_service_name, properties_list)
if not properties_zephyr:
    log_worker.error(f"Failed to identify resource in velocity for Jira Zephyr Service Name {zephyr_service_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)
log_worker.info(f'Opening Jira Zephyr session on {properties_zephyr["ipAddress"]} with user {properties_zephyr["username"]}')
zephyr = ZephyrCore(properties_zephyr["ipAddress"], properties_zephyr["username"], properties_zephyr["password"])
if not zephyr.login():
    log_worker.error(f"Failed to open Jira Zephyr session. Exiting Execution")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

log_worker.info(f'Opening HTML Generator session')
try:
    html_generator = HTMLGenerator("airtel_automation_report.html")
except Exception as e:
    log_worker.error(f"Failed to open HTML Generator sessions. Exiting Execution\n {e}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

# TODO: Get runlist_execution_id from env parameters:
'''Extract Runlist Guid from the current script execution report'''
monitor_report_id = os.environ['VELOCITY_PARAM_REPORT_ID']
monitor_execution_report = velocity_session.get_execution_id(monitor_report_id)
runlist_execution_id = monitor_execution_report["runlistGuid"]

'''DATA PROCESSING - Creating the Zephyr test scenario ID to Velocity Automation Asset test name mapping'''
test_key_script_mapping = {}
if runlist_name == "N/A":
    jira_project_id = __jira_get_project_id(session=jira, project_key=jira_project_key)
    jira_project_version_id = __jira_get_project_version_id(session=jira, project_key=jira_project_key, jira_project_version_name=jira_project_release_name)

    if jira_project_id == 0 or jira_project_version_id == 0:
        log_worker.error(f"Failed to identify IDs for project {jira_project_key} with Version name {jira_project_release_name}")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

    ''' Get Zephyr Cycle ID '''
    zephyr_cycle_id = __zephyr_get_cycle_id(session=zephyr, project_id=jira_project_id, project_version=jira_project_version_id, cycle_name=zephyr_test_cycle_name)
    if zephyr_cycle_id == 0:
        log_worker.error(f"Failed to identify ID for Test Cycle {zephyr_test_cycle_name}")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

    ''' Get Test Keys included in the Zephyr Test Cycle '''
    test_keys_list = __zephyr_get_all_cycle_test_keys(session=zephyr, project_id=jira_project_id, project_version=jira_project_version_id, cycle_id=zephyr_cycle_id)

    for tag in test_keys_list:

        filter_set = {"tags": [tag]}
        automation_assets = velocity_session.get_automation_assets(filters=filter_set)
        if len(automation_assets["content"]) != 0:
            log_worker.debug(f"Found {len(automation_assets['content'])} automation assets mathing tag {tag}")

            test_key_script_mapping[tag] = automation_assets["content"][0]["name"]
            log_worker.info(f"Testcase {automation_assets['content'][0]['name']} was found for tag: {tag}")
        else:
            log_worker.warning(f"No testcases were found for tag: {tag}")
else:
    runlist_info = velocity_session.get_runlist(runlist_name=runlist_name)
    log_worker.debug(f"Runlist info: {runlist_info}")

    for i in range(0, len(runlist_info["main"]["items"])):
        full_path = runlist_info["main"]["items"][i]["path"]
        log_worker.info(f"Testcase full path: {full_path}")
        filter_set = {"fullPath": full_path}
        automation_assets = velocity_session.get_automation_assets(filters=filter_set)

        if len(automation_assets["content"]) == 1 and "airtel_monitor" not in automation_assets["content"][0]["tags"][0] and "airtel_reporter" not in automation_assets["content"][0]["tags"][0]:
            log_worker.debug(f"Following testcases were found while using filter: {filter_set}: {automation_assets}")
            tag = automation_assets["content"][0]["tags"][0]
            test_key_script_mapping[tag] = automation_assets["content"][0]["name"]
        else:
            log_worker.error(f"No testcases were found while using filter: {filter_set}. Request response: {automation_assets}")

if len(test_key_script_mapping.keys()) == 0:
    log_worker.warning(f"No testcases were found for tags {test_keys_list}, exiting execution.")
    sys.exit(0)

'''DATA PROCESSING - Creating the data structures needed for HTML and Jira reporting'''
runlist_data = velocity_session.get_runlist_execution(execution_id=runlist_execution_id)
if len(runlist_data) == 0 or len(runlist_data[0]["executions"]) == 0:
    log_worker.error(f"Runlist has no data or no executions included. Exiting execution.")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

runlist_details = __extract_runlist_details(runlist_data=runlist_data, test_key_script_mapping=test_key_script_mapping, velocity_session=velocity_session)
pass_fail_summary = runlist_details["pass_fail_summary"]
results_data = runlist_details["results_data"]
tests_passed_list = runlist_details["pass_list"]
tests_failed_list = runlist_details["fail_list"]
tests_indeterminate_list = runlist_details["indeterminate_list"]
tests_not_executed_list = runlist_details["not_run_list"]
runlist_link = f"https://{velocity}/velocity/reports/runlists/{runlist_execution_id}"

''' REPORTING - Generate HTML Report '''
current_time = datetime.now().strftime("%d-%m-%Y_%Hh%Mm%Ss")
html_report_file = os.path.join(REPORTINGPARAMS["report_path"], f"auto_report_{zephyr_test_cycle_name}_{zephyr_build}_{current_time}.html")
html_generation_result = html_generator.airtel_report_generator(output_file=html_report_file,
                                                     test_cycle=zephyr_test_cycle_name, build=zephyr_build,
                                                     runlist_link=runlist_link,
                                                     time_date=current_time, pass_fail_summary=pass_fail_summary,
                                                     results_data=results_data,
                                                     not_run_list=tests_not_executed_list)

if html_generation_result:
    log_worker.info(f"HTML report was generated successfully under {html_report_file}.")
else:
    log_worker.error(f"Failed to generate the HTML report. Exiting Execution")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)


''' REPORTING - Update JIRA '''
if story_key_for_comment:
    jira_reporting_failed = 0
    comment = __build_comment(project_key=jira_project_key,
                                        project_version_name=jira_project_release_name,
                                        cycle_name=zephyr_test_cycle_name,
                                        runlist_link=runlist_link, pass_fail_summary=pass_fail_summary,
                                        update_pass_list=tests_passed_list, update_fail_list=tests_failed_list,
                                        update_not_run_list=tests_not_executed_list,
                                        attachment_location=html_report_file)
    if not jira.add_comment(item_key=story_key_for_comment, content=comment):
        log_worker.error(f"Failed to add comment in Jira story {story_key_for_comment}. Exiting Execution")
        jira_reporting_failed = 1

    if not jira.attach_file(item_key=story_key_for_comment, file_path=html_report_file):
        log_worker.error(f"Failed to attach file {story_key_for_comment} in Jira story {story_key_for_comment}. Exiting Execution")
        jira_reporting_failed = 1

    if not jira_reporting_failed:
        log_worker.info(f"Added comment in Jira story {story_key_for_comment}.")
    else:
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

log_worker.info(f"Finished: PASSED")