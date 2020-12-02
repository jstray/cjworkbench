import React from 'react'
import PropTypes from 'prop-types'
import { t } from '@lingui/macro'
import { withI18n } from '@lingui/react'
import IconAddc from '../../../icons/addc.svg'

export class NewTabPrompt extends React.PureComponent {
  static propTypes = {
    create: PropTypes.func.isRequired // func() => undefined
  }

  render () {
    const { create, i18n } = this.props
    return (
      <button title={i18n._(t('js.WorkflowEditor.Tabs.NewTabPrompt.createTab.title')`Create tab`)} className='new-tab' onClick={create}>
        <IconAddc />
      </button>
    )
  }
}

export default withI18n()(NewTabPrompt)
