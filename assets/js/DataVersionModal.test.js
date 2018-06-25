import React from 'react'
import { mount } from 'enzyme'
import ConnectedDataVersionModal, { DataVersionModal } from './DataVersionModal'
import { Provider } from 'react-redux'
import configureMockStore from 'redux-mock-store'

describe('DataVersionModal', () => {
  const Versions = [
    { id: '2000', date: new Date(234567890), isSeen: false },
    { id: '1000', date: new Date(123456789), isSeen: true },
  ]

  let _wrapper = null

  afterEach(() => {
    if (_wrapper !== null) {
      _wrapper.unmount()
      _wrapper = null
    }
  })

  const wrapper = (extraProps) => {
    return _wrapper = mount(
      <DataVersionModal
        fetchWfModuleId={123}
        fetchWfModuleName={'fetch'}
        fetchVersions={Versions}
        selectedFetchVersionId={'1000'}
        wfModuleId={124}
        isAnonymous={false}
        notificationsEnabled={false}
        onClose={jest.fn()}
        onChangeFetchVersionId={jest.fn()}
        onChangeNotificationsEnabled={jest.fn()}
        {...extraProps}
        />
    )
  }

  it('matches snapshot', () => {
    expect(wrapper()).toMatchSnapshot()
  })

  it('displays versions', () => {
    const w = wrapper()
    expect(w.find('label.seen.selected time').text()).toEqual('Jan. 2, 1970 – 10:17 a.m.')
    expect(w.find('label.unseen time').text()).toEqual('Jan. 3, 1970 – 5:09 p.m.')
  })

  it('selects a version', () => {
    const w = wrapper()

    // Click new version; verify it's clicked
    w.find('label.unseen input').simulate('change', { target: { checked: true } })
    expect(w.find('label.unseen input').prop('checked')).toBe(true)

    // Click 'Load'
    w.find('button[name="load"]').simulate('click')
    expect(w.prop('onChangeFetchVersionId')).toHaveBeenCalledWith(123, '2000')
    expect(w.prop('onClose')).toHaveBeenCalled()
  })

  it('cancels with a close button', () => {
    const w = wrapper()

    // Click new version; verify it's clicked
    w.find('label.unseen input').simulate('change', { target: { checked: true } })

    w.find('button.close').simulate('click')
    expect(w.prop('onClose')).toHaveBeenCalled()
  })

  it('enables/disables notifications', () => {
    const w = wrapper()

    w.find('input[name="notifications-enabled"]').simulate('change', { target: { checked: true } })
    expect(w.prop('onChangeNotificationsEnabled')).toHaveBeenCalledWith(124, true)
    w.setProps({ notificationsEnabled: true }) // simulate onChangeNotificationsEnabled()
    expect(w.find('input[name="notifications-enabled"]').prop('checked')).toBe(true)

    w.find('input[name="notifications-enabled"]').simulate('change', { target: { checked: false } })
    expect(w.prop('onChangeNotificationsEnabled')).toHaveBeenCalledWith(124, true)
    w.setProps({ notificationsEnabled: false }) // simulate onChangeNotificationsEnabled()
    expect(w.find('input[name="notifications-enabled"]').prop('checked')).toBe(false)
  })

  it('omits notifications settings when isAnonymous', () => {
    const w = wrapper({ isAnonymous: true })
    expect(w.find('form.notifications').length).toBe(0)
  })

  describe('mapStateToProps', () => {
    // Assume this modal is never shown if there is no fetch module
    const IdealState = {
      workflow: {
        is_anonymous: false,
        wf_modules: [
          {
            id: 123,
            notifications: true,
            module_version: { module: { loads_data: true, name: 'Fetch Stuff' } },
            versions: {
              versions: [ 
                [ '2018-06-22T20:09:41.649Z', true ],
                [ '2018-06-23T20:09:41.649Z', false ],
              ],
              selected: '2018-06-22T20:09:41.649Z',
            }
          },
          {
            id: 124,
            name: 'Filter Stuff',
            notifications: true,
            module_version: { module: { loads_data: false, name: 'Filter Stuff' } },
          }
        ]
      }
    }

    const connectedWrapper = (state) => {
      const store = configureMockStore([])(state)
      return _wrapper = mount(
        <Provider store={store}>
          <ConnectedDataVersionModal
            wfModuleId={124}
            onClose={jest.fn()}
            />
        </Provider>
      )
    }

    it('should find notificationsEnabled', () => {
      const w = connectedWrapper(IdealState)
      expect(w.find('input[name="notifications-enabled"]').prop('checked')).toBe(true)
    })

    it('should set fetchModuleName', () => {
      const w = connectedWrapper(IdealState)
      expect(w.find('p.introduction').text()).toMatch(/“Fetch Stuff”/)
    })

    it('should set fetchVersions', () => {
      const w = connectedWrapper(IdealState)

      expect(w.find('label.selected time[time="2018-06-22T20:09:41.649Z"]').length).toBe(1)
      expect(w.find('label.unseen time[time="2018-06-23T20:09:41.649Z"]').length).toBe(1)
    })
  })
})
