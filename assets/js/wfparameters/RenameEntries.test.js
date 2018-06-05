import React from 'react'
import RenameEntries, {mockAPI} from './RenameEntries'
import {mount, shallow} from 'enzyme'
import {jsonResponseMock} from "../test-utils";


describe('ReorderEntries rendering and interactions', () => {
    const testEntries = {
        'name': 'host_name',
        'narrative': 'nrtv'
    };

    const columns = ['name', 'build_year', 'narrative', 'cornerstone'];

    beforeEach(() => {
        const api = {
            inputColumns: jsonResponseMock(columns),
            onParamChanged: jest.fn().mockReturnValue(Promise.resolve())
        };
        mockAPI(api);
    });

    it('Displays all columns when displayAll is set to true', (done) => {
        let tree = mount(<RenameEntries
            displayAll={true}
            entries={JSON.stringify({})}
            wfModuleId={1}
            paramId={2}
        />);

        setImmediate(() => {
            // Got the tip to call .update() in this thread:
            // https://github.com/airbnb/enzyme/issues/1233#issuecomment-343449560
            tree.update();
            expect(tree.find('.rename-input')).toHaveLength(4);
            expect(tree.find('.rename-input').get(0).props.value).toEqual('name');
            expect(tree.find('.rename-input').get(1).props.value).toEqual('build_year');
            expect(tree.find('.rename-input').get(2).props.value).toEqual('narrative');
            expect(tree.find('.rename-input').get(3).props.value).toEqual('cornerstone');
            tree.unmount();
            done();
        });
    });

    it('Displays changed columns properly when displayAll is set to true', (done) => {
        let tree = mount(<RenameEntries
            displayAll={true}
            entries={JSON.stringify(testEntries)}
            wfModuleId={1}
            paramId={2}
        />);

        setImmediate(() => {
            // Got the tip to call .update() in this thread:
            // https://github.com/airbnb/enzyme/issues/1233#issuecomment-343449560
            tree.update();
            expect(tree.find('.rename-input')).toHaveLength(4);
            expect(tree.find('.rename-input').get(0).props.value).toEqual('host_name');
            expect(tree.find('.rename-input').get(1).props.value).toEqual('build_year');
            expect(tree.find('.rename-input').get(2).props.value).toEqual('nrtv');
            expect(tree.find('.rename-input').get(3).props.value).toEqual('cornerstone');
            tree.unmount();
            done();
        });
    });

    it('Only displays changed columns when displayAll is set to false', (done) => {
        let tree = mount(<RenameEntries
            displayAll={false}
            entries={JSON.stringify(testEntries)}
            wfModuleId={1}
            paramId={2}
        />);

        setImmediate(() => {
            // Got the tip to call .update() in this thread:
            // https://github.com/airbnb/enzyme/issues/1233#issuecomment-343449560
            tree.update();
            expect(tree.find('.rename-input')).toHaveLength(2);
            expect(tree.find('.rename-input').get(0).props.value).toEqual('host_name');
            expect(tree.find('.rename-input').get(1).props.value).toEqual('nrtv');
            tree.unmount();
            done();
        });
    });
});