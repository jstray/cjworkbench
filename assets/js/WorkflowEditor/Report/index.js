import Dashboard from './Dashboard'
import { connect } from 'react-redux'
import selectReport from '../../selectors/selectReport'
import selectReportableTabs from '../../selectors/selectReportableTabs'
import selectIsReadOnly from '../../selectors/selectIsReadOnly'
import {
  addBlock,
  deleteBlock,
  reorderBlocks,
  setBlockMarkdown
} from './actions'

function mapStateToProps (state) {
  return {
    workflow: state.workflow,
    blocks: selectReport(state),
    reportableTabs: selectReportableTabs(state),
    isReadOnly: selectIsReadOnly(state)
  }
}

const mapDispatchToProps = {
  addBlock,
  deleteBlock,
  reorderBlocks,
  setBlockMarkdown
}

export default connect(mapStateToProps, mapDispatchToProps)(Dashboard)
