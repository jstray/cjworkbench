import React from 'react'
import PropTypes from 'prop-types'
import { MaybeLabel } from './util'

/**
 * A file-upload field.
 *
 * A file-upload field actually maintains a _list_ of file uploads, even
 * though the user only sees one at a time. (This is cruft: we used to
 * support "Versions" of files, it's expensive to _remove_ that feature now,
 * even though it's rarely used.) The `value` is a UUID; the `files` prop
 * is a list of UploadedFiles that must include `value`.
 *
 * Features:
 *
 * User can change `value` by opening a Modal that shows all `files`.
 * User can change `value` by uploading a new file.
 * After changing `value`, we auto-submit our new params.
 * Prompts user when `value` is not in `files`.
 */
export default class FileField extends React.PureComponent {
  static propTypes = {
    isReadOnly: PropTypes.bool.isRequired,
    onChange: PropTypes.func.isRequired, // onChange(n) => undefined
    onSubmit: PropTypes.func.isRequired, // onSubmit() => undefined
    name: PropTypes.string.isRequired, // <input name=...>
    files: PropTypes.arrayOf(PropTypes.shape({
      uuid: PropTypes.string.isRequired,
      name: PropTypes.string.isRequired,
      createdAt: PropTypes.string.isRequired // ISO8601-formatted date
    }).isRequired).isRequired,
    wfModuleId: PropTypes.number.isRequired,
    fieldId: PropTypes.string.isRequired,
    value: PropTypes.string, // String-encoded UUID or null
    upstreamValue: PropTypes.string, // String-encoded UUID or null
    startUpload: PropTypes.func.isRequired, // func(wfModuleId, onProgress, cancel) => undefined
  }

  state = {
    upload: null, // { uuid, name, progress } Object
  }

  render () {
    const { name, value, files, fieldId, isReadOnly } = this.props
    const { upload } = this.state
    const file = files.find(f => f.uuid === value)

    return (
      <React.Fragment>
        {upload ? (
          <div className='uploading-file'>
            <div className='filename'>{upload.name}</div>
            <div className='status'>
              <VersionSelect isReadOnly={isReadOnly} value={value} files={files} onClick={this.onChange} />
              <button type='button' onClick={this.cancel} name='cancel-upload' title='Cancel upload'>
                Cancel Upload
              </button>
            </div>
          </div>
        ) : (file ? (
          <div className='existing-file'>
            <div className='filename'>{file.name}</div>
            <div className='status'>
              <VersionSelect isReadOnly={isReadOnly} value={value} files={files} onClick={this.onChange} />
              <p className='replace-button'>
                Replace
                <input
                  type='file'
                  name={name}
                  id={fieldId}
                  readOnly={isReadOnly}
                  onChange={this.uploadFile}
                />
              </p>
            </div>
          </div>
        ) : (
          <div className='no-file'>
            <p>Drag file here</p>
            <p>or</p>
            <p className='browse-button'>Browse</p>
            <input
              type='file'
              name={name}
              id={fieldId}
              readOnly={isReadOnly}
              onChange={this.uploadFile}
            />
          </div>
        ))}
      </React.Fragment>
    )
  }
}
