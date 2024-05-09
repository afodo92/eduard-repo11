import json
import os
import sys
import time
import argparse

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import helpers.Logger as Local_logger
import libs.libs_velocity.Velocity as Velocity
from libs.libs_zephyr.ZephyrCore import ZephyrCore
from parameters.global_parameters import Reporting as REPORTINGPARAMS
from parameters.global_parameters import Jira as JIRAPARAMS
from parameters.global_parameters import Zephyr as ZEPHYRPARAMS
from parameters.global_parameters import Velocity as VELOCITYPARAMS
from libs.libs_jira.JiraCore import JiraCore

log_worker = Local_logger.create_logger(__name__, REPORTINGPARAMS["log_level_default"],
                                        REPORTINGPARAMS["test_log_path"], "run_phase_2_monitor.txt")


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

'''Initializing arguments'''
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
print(parser.parse_known_args()[0])
validate_data_empty = {"jira_project_key":jira_project_key, "jira_project_release_name":jira_project_release_name, "zephyr_test_cycle_name":zephyr_test_cycle_name,
                       "story_key_for_comment": story_key_for_comment, "zephyr_build":zephyr_build, "runlist_name":runlist_name, "topology_name":topology_name,
                       "zephyr_test_cycle_id":zephyr_test_cycle_id}
for input_parameter in validate_data_empty.keys():
    if validate_data_empty[input_parameter] == "":
        log_worker.error(f"Argument {input_parameter} is empty, exiting execution. Set to specific value or N/A")
        log_worker.error(f"Finished: FAILED")
        sys.exit(0)

velocity = VELOCITYPARAMS['host']
velo_user = VELOCITYPARAMS['user']
velo_password = VELOCITYPARAMS['pass']

'''Open Velocity Session'''
try:
    velocity_session = Velocity.API(velocity, velo_user, velo_password)
except Exception as e:
    log_worker.error(f"Failed to open Velocity session. Exiting Execution\n {e}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

'''Open Jira Session'''
jira_service_name = JIRAPARAMS['service_name_velo']
properties_list = ['ipAddress', 'username', 'password']
properties_jira = velocity_session.get_resource_property_value(jira_service_name, properties_list)
if not properties_jira:
    log_worker.error(f"Failed to identify resource in velocity for Jira Service Name {jira_service_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)
log_worker.info(f'Opening Jira session on {properties_jira["ipAddress"]} with user {properties_jira["username"]}')
try:
    jira_session = JiraCore(properties_jira["ipAddress"], properties_jira["username"], properties_jira["password"])
except Exception as e:
    log_worker.error(f"Failed to open Jira session. Exiting Execution\n {e}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

'''Open Zephyr Session'''
zephyr_service_name = ZEPHYRPARAMS['service_name_velo']
properties_list = ['ipAddress', 'username', 'password']
properties_zephyr = velocity_session.get_resource_property_value(zephyr_service_name, properties_list)
if not properties_jira:
    log_worker.error(f"Failed to identify resource in velocity for Jira Zephyr Service Name {zephyr_service_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)
log_worker.info(f'Opening Jira Zephyr session on {properties_zephyr["ipAddress"]} with user {properties_zephyr["username"]}')
zephyr_session = ZephyrCore(properties_zephyr["ipAddress"], properties_zephyr["username"], properties_zephyr["password"])
if not zephyr_session.login():
    log_worker.error(f"Failed to open Jira Zephyr session. Exiting Execution")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

'''Extract Runlist Guid from the current script execution report'''
monitor_report_id = os.environ['VELOCITY_PARAM_REPORT_ID']
monitor_execution_report = velocity_session.get_execution_id(monitor_report_id)
monitor_runlist_item_number = monitor_execution_report["runlistItemId"]
runlist_guid = monitor_execution_report["runlistGuid"]

# TODO: Identify the result for the previously exected script: text_case_report_id and test_case_result
runlist_summary = velocity_session.get_runlist_execution(runlist_guid)[0]["executions"]
test_case_summary = [i for i in runlist_summary if i["runlistItemId"] == str(int(monitor_runlist_item_number) - 1)]
test_case_report_id = test_case_summary[0]["executionID"]

for attempt in range(10):
    execution_details = velocity_session.get_execution_id(execution_id=test_case_report_id)
    if type(execution_details) is not dict:
        execution_details = json.loads(execution_details)
    test_case_result = execution_details["result"]

    if test_case_result == "INDETERMINATE":
        log_worker.warning(f"Testcase {test_case_report_id} has executionState COMPLETED but result is INDETERMINATE. Attempt: {attempt + 1}.")
        time.sleep(1)
    else:
        break

test_case_name = execution_details.get("testPath").split("/")[-1]
full_path = execution_details["testPath"]
log_worker.info(f"Testcase full path: {full_path}")
filter_set = {"fullPath": full_path}
automation_assets = velocity_session.get_automation_assets(filters=filter_set)
if len(automation_assets["content"]) != 1 or len(automation_assets["content"][0]["tags"]) != 1:
    test_case_tag = None
    log_worker.error(f"Testcase was not identified by full path or has inconsistent tag information.\nSee data returned by Velocity: {automation_assets}")
else:
    test_case_tag = automation_assets["content"][0]["tags"][0]
    log_worker.info(f"Testcase tag was identified {test_case_tag}")

test_case_execution_link = f"https://{velocity}/velocity/reports/executions/{execution_details.get('executionID')}"
test_case_failure_reason = execution_details.get("failureReason") if execution_details.get("failureReason") else \
    velocity_session.get_execution_failure_reason(execution_details.get("executionID"))

if not test_case_tag:
    log_worker.error(f"Failed to identify Test Case Tag (Zephyr Key) for test with name {test_case_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

# TODO: If test result is failed, open Jira defect ID
open_defect = None
if test_case_result.lower() in ["fail", "indeterminate"]:
    log_worker.info(f"Execution result for Test {test_case_name} is {test_case_result}. Opening Jira defect.")
    test_case_failure_reason = test_case_failure_reason.replace('"', '')
    open_defect = jira_session.open_defect(jira_project_key, summary=f"{test_case_tag} - {test_case_name} has failed.",
                                   description=f"Test Name: {test_case_name}\n"
                                               f"Test Tag: {test_case_tag} (to map to Zephyr)\n"
                                               f"Execution Failure reason: {test_case_failure_reason}\n\n"
                                               f"Link to the Velocity execution report: {test_case_execution_link}")
    if open_defect:
        log_worker.info(f"Jira defect {open_defect} has been opened.")
        link_result = jira_session.link_item(open_defect, story_key_for_comment, "relates")
        if link_result:
            log_worker.info(f"Jira defect {open_defect} has been linked to {story_key_for_comment}.")
        else:
            log_worker.error(f"Failed to link Jira defect {open_defect} to {story_key_for_comment}.")
    else:
        log_worker.error(f"Failed to open Jira defect.")

# TODO: Update Zephyr result for the test with specific Tag and result from above
jira_project_id = __jira_get_project_id(session=jira_session, project_key=jira_project_key)
if jira_project_id == 0:
    log_worker.error(f"Failed to identify IDs for project {jira_project_key} with Version name {jira_project_release_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

jira_project_version_id = __jira_get_project_version_id(session=jira_session, project_key=jira_project_key, jira_project_version_name=jira_project_release_name)
if jira_project_version_id == 0:
    log_worker.error(f"Failed to identify IDs for project {jira_project_key} with Version name {jira_project_release_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

test_case_key_to_execution_id = __zephyr_get_all_cycle_test_keys_with_execution_ids(session=zephyr_session, project_id=jira_project_id, project_version=jira_project_version_id, cycle_id=zephyr_test_cycle_id)
if test_case_tag not in test_case_key_to_execution_id.keys():
    log_worker.error(f"Test Case with Tag (Zephyr Key) {test_case_tag} is not present in the Test Cycle {zephyr_test_cycle_name}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

if not zephyr_session.update_test_execution_status_by_id(execution_id=test_case_key_to_execution_id[test_case_tag], execution_status=test_case_result):
    log_worker.error(f"Failed to update Test Result in Zephyr Test Cycle {zephyr_test_cycle_name} for Test Case with Tag (Zephyr Key) {test_case_tag}")
    log_worker.error(f"Finished: FAILED")
    sys.exit(0)

log_worker.info(f"Finished: PASSED")