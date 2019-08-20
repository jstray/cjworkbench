import React from 'react'
import PropTypes from 'prop-types'
import { Modal, ModalHeader, ModalBody, ModalFooter } from '../../components/Modal'
import { getApiToken, clearApiToken, resetApiToken } from './actions'
import { connect } from 'react-redux'

class ApiTokenState {
  constructor (flag, apiToken) {
    this.flag = flag
    this.apiToken = apiToken
  }
}
ApiTokenState.OK = 0
ApiTokenState.LOADING = 1
ApiTokenState.SENDING = 2

function ApiToken ({ workflowId, wfModuleSlug, apiTokenState, clearApiToken, resetApiToken }) {
  switch (apiTokenState.flag) {
    case ApiTokenState.OK: return <ApiTokenOk workflowId={workflowId} wfModuleSlug={wfModuleSlug} apiToken={apiTokenState.apiToken} clearApiToken={clearApiToken} resetApiToken={resetApiToken} />
    case ApiTokenState.LOADING: return <ApiTokenLoading />
    case ApiTokenState.SENDING: return <ApiTokenSending />
  }
}

function ApiTokenLoading () {
  return <div className='state-loading'>Loading</div>
}

function ApiTokenSending () {
  return <div className='state-sending'>…</div>
}

function ApiTokenOk ({ workflowId, wfModuleSlug, apiToken, clearApiToken, resetApiToken }) {
  return (
    <div className='state-ok'>
      {apiToken ? (
        <>
          <p className='api-token'>
            <strong>API Token</strong>:
            <code>{apiToken}</code>
            <button type='button' name='reset-api-token' onClick={resetApiToken}>Reset API token</button>
            <button type='button' name='clear-api-token' onClick={clearApiToken}>Disable API</button>
          </p>
          <p className='workflow-id'>
            <strong>Workflow ID</strong>:
            <code>{workflowId}</code>
          </p>
          <p className='step-slug'>
            <strong>Step ID</strong>:
            <code>{wfModuleSlug}</code>
          </p>
        </>
      ) : (
        <p className='no-api-token'>
          <span>No API token</span>
          <button type='button' name='reset-api-token' onClick={resetApiToken}>Enable API</button>
        </p>
      )}
    </div>
  )
}

function Instructions ({ workflowId, wfModuleSlug, apiToken }) {
  const varsCode = [
    `WorkflowId = "${workflowId}"`,
    `StepId = "${wfModuleSlug}"`,
    `ApiToken = "${apiToken}"`,
    'FileToUpload = "/path/to/test.csv"',
    'Filename = "test.csv"  # name that appears in Workbench'
  ].join('\n')

  const importsCode = [
    'import boto3',
    'import botocore',
    'import requests'
  ].join('\n')

  const postUrl = `${window.location.origin}/api/v1/workflows/{WorkflowId}/steps/{StepId}/uploads`

  const postCode = [
    `credentials_url = f"${postUrl}"`,
    'credentials_response = requests.post(',
    '    credentials_url,',
    '    headers={"Authorization": f"Bearer {ApiToken}"}',
    ')',
    'credentials_response.raise_for_status()  # expect 200 OK',
    's3_config = credentials_response.json()'
  ].join('\n')

  const uploadCode = [
    's3_client = boto3.client(',
    '    \'s3\',',
    '    aws_access_key_id=s3_config["credentials"]["accessKeyId"],',
    '    aws_secret_access_key=s3_config["credentials"]["secretAccessKey"],',
    '    aws_session_token=s3_config["credentials"]["sessionToken"],',
    '    region_name=s3_config["region"],',
    '    endpoint_url=s3_config["endpoint"],',
    '    config=botocore.client.Config(s3={"addressing_style": "path"}),',
    ')',
    's3_client.upload_file(FileToUpload, s3_config["bucket"], s3_config["key"])'
  ].join('\n')

  const finishCode = [
    'finish_response = requests.post(',
    '    s3_config["finishUrl"],',
    '    headers={"Authorization": f"Bearer {ApiToken}"},',
    '    json={"filename": Filename},',
    ')',
    'finish_response.raise_for_status()  # expect 200 OK'
  ].join('\n')

  return (
    <>
      <h5>How to upload</h5>
      <p>Each file you upload belongs in a unique <a href='https://aws.amazon.com/s3/'>Amazon S3</a>-compatible endpoint. You cannot reuse the same endpoint for two files: to replace a file, you must follow all these steps again.</p>
      <p>These instructions use Python 3, for illustration. You may use any programming language.</p>
      <p>A good way to start your project is to copy and paste all this code into a script (one step at a time), and then edit.</p>
      <h6>0. Install and load dependencies</h6>
      <p>Your program will need to make HTTP requests and upload to S3.</p>
      <pre>{importsCode}</pre>
      <p><a href='https://aws.amazon.com/sdk-for-python/'>boto3</a> is the AWS SDK for Python. There is an <a href='https://aws.amazon.com/tools/'>AWS SDK</a> for most any programming language; and there are dozens of third-party libraries that are compatible with Workbench. Use any library that supports custom endpoints, session tokens and "path" addressing style.</p>
      <p><a href='https://2.python-requests.org/en/master/'>requests</a> is an HTTP library with simpler requests than Python's built-in <a href='https://docs.python.org/3/library/urllib.request.html'>urllib.request</a>.</p>
      <h6>1. Store variables and secrets</h6>
      <pre>{varsCode}</pre>
      <p><strong>Do not share the API token or commit it to any code repository.</strong> Anybody with access to the token can alter this step. Keep it safe. If you suspect your API token has been compromised, reset the API token.</p>
      <h6>1. Query Workbench for upload credentials</h6>
      <p>Send an HTTP POST request to <code>{postUrl}</code>. It should have no parameters or content. (Do not upload the file to this URL.) It must have an <code>Authorization</code> header that looks like <code>Bearer [ApiToken]</code>.</p>
      <pre>{postCode}</pre>
      <p><code>s3_config</code> will be a dictionary with the following keys:</p>
      <ul>
        <li><code>endpoint</code>: URL of S3-compatible upload server</li>
        <li><code>region</code>: S3-compatible region code</li>
        <li><code>bucket</code>: S3 bucket name where your file should be uploaded</li>
        <li><code>key</code>: S3 key name where your file should be uploaded</li>
        <li><code>credentials</code>: Dictionary with <code>accessKeyId</code>, <code>secretAccessKey</code> and <code>sessionToken</code> keys</li>
        <li><code>finishUrl</code>: (non-S3) URL to notify when we're done using the S3 API</li>
      </ul>
      <p>The credentials will only allow you to upload your file to the specified <code>bucket</code> and <code>key</code>. The credentials will expire in a few hours.</p>
      <h6>2. Upload to S3-compatible bucket</h6>
      <pre>{uploadCode}</pre>
      <p>See the <a href='https://aws.amazon.com/tools/'>AWS SDK documentation</a> for your library to learn how to upload a file.</p>
      <h6>3. Tell Workbench to finish the upload, and give it a filename</h6>
      <pre>{finishCode}</pre>
      <p>In your workflow, this Step will be updated to use the new file.</p>
    </>
  )
}

export const UploadApiModal = React.memo(function UploadApiModal ({ wfModuleId, wfModuleSlug, workflowId, onClickClose, getApiToken, resetApiToken, clearApiToken }) {
  const [apiTokenState, setApiTokenState] = React.useState(new ApiTokenState(ApiTokenState.LOADING, null))
  const { apiToken } = apiTokenState
  React.useEffect(() => {
    getApiToken(wfModuleId).then(({ value }) => value).then(apiToken => setApiTokenState(new ApiTokenState(ApiTokenState.OK, apiToken)))
  }, [wfModuleId])
  const doResetApiToken = React.useCallback(() => {
    setApiTokenState(new ApiTokenState(ApiTokenState.SENDING, apiTokenState.apiToken))
    resetApiToken(wfModuleId).then(({ value }) => value).then(apiToken => setApiTokenState(new ApiTokenState(ApiTokenState.OK, apiToken)))
  })
  const doClearApiToken = React.useCallback(() => {
    setApiTokenState(new ApiTokenState(ApiTokenState.SENDING, null))
    clearApiToken(wfModuleId).then(({ value }) => value).then(apiToken => setApiTokenState(new ApiTokenState(ApiTokenState.OK, null)))
  })

  return (
    <Modal className='upload-api-modal' isOpen size='lg' toggle={onClickClose}>
      <ModalHeader>UPLOAD BY API</ModalHeader>
      <ModalBody>
        <h5>These instructions are for programmers.</h5>
        <p>The file-upload API is perfect for loading data from cronjobs or other external scripts. You can send data to Workbench using any programming language.</p>
        {apiToken ? (
          <p>The file-upload API is <strong>enabled</strong>.</p>
        ) : (
          <p>The file-upload API is disabled. Please enable it to allow uploading.</p>
        )}
        <ApiToken
          workflowId={workflowId}
          wfModuleSlug={wfModuleSlug}
          apiTokenState={apiTokenState}
          resetApiToken={doResetApiToken}
          clearApiToken={doClearApiToken}
        />
        {apiToken ? (
          <Instructions workflowId={workflowId} wfModuleSlug={wfModuleSlug} apiToken={apiToken} />
        ) : null}
      </ModalBody>
      <ModalFooter>
        <div className='actions'>
          <button
            name='close'
            className='action-button button-gray'
            onClick={onClickClose}
          >Close
          </button>
        </div>
      </ModalFooter>
    </Modal>
  )
})
UploadApiModal.propTypes = {
  workflowId: PropTypes.number.isRequired,
  wfModuleId: PropTypes.number.isRequired,
  wfModuleSlug: PropTypes.string.isRequired,
  onClickClose: PropTypes.func.isRequired // () => undefined
}

const mapDispatchToProps = { getApiToken, clearApiToken, resetApiToken }
export default connect(null, mapDispatchToProps)(UploadApiModal)
