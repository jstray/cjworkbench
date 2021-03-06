import { createSelector } from 'reselect'
import selectOptimisticState from './selectOptimisticState'
import selectWorkflowAclLookup from './selectWorkflowAclLookup'

const selectLoggedInUser = (state) => state.loggedInUser
const selectOwnerEmail = (state) => state.workflow.owner_email

const selectLoggedInUserRoleFromOptimisticState = createSelector(
  selectLoggedInUser,
  selectOwnerEmail,
  selectWorkflowAclLookup,
  (user, ownerEmail, aclLookup) => {
    if (user && user.email === ownerEmail) {
      return 'owner'
    }
    if (!user && !ownerEmail) {
      // anonymous workflow => can't be shared, so whoever sees it owns it
      return 'owner'
    }
    if (user) {
      return aclLookup[user.email] || 'viewer'
    }
    return 'viewer'
  }
)

/**
 * Select the logged-in (or anonymous) user's role.
 *
 * Valid roles: "owner", "editor", "viewer".
 *
 * (The "report-viewer" role won't come up, because report viewers can't read
 * the workflow or ACL in the first place.)
 */
const selectLoggedInUserRole = createSelector(
  selectOptimisticState,
  selectLoggedInUserRoleFromOptimisticState
)
export default selectLoggedInUserRole
